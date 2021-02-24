import time
from rq import get_current_job
from app import create_app
from app.config import config_by_name
from app.models.tasks import *
from app.models.olt import *
from app.models.ont import *
from app.models.interfaces import *
from app.models.device_models import *
from app.api.service.ont_service import (
    get_ont,
    get_ont_profiles,
    get_ont_vlans,
)
from app.api.service.olt_service import get_olt
from app.api.service.interfaces_service import get_interface
import os
import datetime
import logging
from app.libs.dasan_reader import DasanReader
import re
import ipaddress
import traceback
from flask_restplus import marshal
from app.api.util.dto import ONTDto, DeviceModelDto
from app.api.util.helpers import return_success, return_error, safe_commit
import traceback


libLogger = logging.getLogger("main." + __name__)
app = create_app(os.getenv("ENV_TYPE") or "dev")
app.app_context().push()

_ont = ONTDto.ont
_device_model = DeviceModelDto.device_model
_ont_wifi = ONTDto.ont_wifi
_ont_voip = ONTDto.ont_voip
_ont_catv = ONTDto.ont_catv
_ont_vlans = ONTDto.ont_vlans
_ont_profiles = ONTDto.ont_profiles
_onts_profiles = ONTDto.onts_profiles


def return_error(msg, return_code):
    response_object = {"status": "fail", "message": msg}
    return response_object, return_code


def updateTask(taskID, message, status="info", finish=False, progress=0):
    """Update task and create log entry
    :parameter taskID: The redis job ID
    :type taskID:int
    :parameter message: Log message
    :type message:string
    :parameter status: Then log status:info, warning or error
        (default is info)
    :type status:string
    :parameter finish
    :type status:bool
    :parameter progress: The task progress (0-100)
    """
    if taskID is None:
        return

    if status not in ["error", "warning", "info"]:
        libLogger.error("The level must be error, warning or info")
        return False

    task = (
        db.session.query(Task)
        .filter(Task.id == taskID, Task.completed_at == None)
        .first()
    )
    if not task:
        libLogger.exception("Failed to find active taskID %d", taskID)
        return False

    if progress > 0:
        _set_task_progress(progress)
    if progress > 1:
        task.status = "running"

    newLog = TaskLogs(task_id=task.id, status=status, log=message)
    db.session.add(newLog)

    if finish is True:
        task.completed = True
        task.completed_at = datetime.datetime.now()
        task.status = "success"
        if status == "error":
            task.status = "failed"

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        libLogger.error("session.rollback()")
    libLogger.log(5, "DBLOG for %s. %s => %s", taskID, status, message)

    if finish is True:
        db.session.close()
    return True


def _set_task_progress(progress):
    job = get_current_job()
    if job:
        job.meta["progress"] = progress
        job.save_meta()
        task = Task.query.get(job.get_id())
        if progress >= 100:
            task.completed = True


def range_expand(s):
    """Takes a range in form of "a-b" and generate a list of numbers between a and b inclusive.
    Also accepts comma separated ranges like "a-b,c-d,f" will build a list which will include
    Numbers from a to b, c to d and f"""
    s = "".join(s.split())  # removes white space
    r = set()
    for x in s.split(","):
        t = x.split("-")
        if len(t) not in [1, 2]:
            raise SyntaxError(
                "hash_range is given its arguement as "
                + s
                + " which seems not correctly formated."
            )
        r.add(int(t[0])) if len(t) == 1 else r.update(
            set(range(int(t[0]), int(t[1]) + 1))
        )
    l = list(r)
    l.sort()
    return [str(x) for x in l]


def check_all_olts_status(username="system"):
    job = get_current_job()
    task = Task(
        id=job.get_id(),
        name="check_all_olts_status",
        description=f"Verifica statusul si uptime-ul tuturor olt-urilor",
        username=username,
    )
    db.session.add(task)
    db.session.commit()
    olts = OLT.query.all()
    for olt in olts:
        ds = DasanReader(olt)
        rez = ds.snmp_query(".1.3.6.1.2.1.1.3.0")
        if rez:
            olt.status = "online"
            olt.last_update = datetime.datetime.now()
        else:
            olt.status = "offline"
        try:
            db.session.add(olt)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            libLogger.error(f"Error saving status for olt {olt.hostname}: {str(e)}")
            libLogger.debug(traceback.format_exc())
    updateTask(
        task.id,
        "Verificarea s-a finalizat",
        progress=100,
        finish=True,
    )
    db.session.commit()


def import_slots(olt, data):
    job = get_current_job()
    task = Task(
        id=job.get_id(),
        name="import_slots",
        description=f"import slots from olt {olt.hostname}",
        username=data["username"],
    )
    db.session.add(task)
    db.session.commit()
    try:
        libLogger.info("Starting import slots task")
        updateTask(task.id, " Se preiau informatii despre slot-uri", progress=5)
        ds = DasanReader(olt)
        if not ds.telnetConnect():
            updateTask(
                task.id,
                "Eroare la conectarea pe olt",
                progress=100,
                status="error",
                finish=True,
            )
            libLogger.error(f"Eroare la conectarea pe olt")
            return return_error("Eroare la conectarea pe olt", 400)
        dsSlots = ds.readSlots()
        dashline = 0
        name = (
            model
        ) = (
            serial
        ) = (
            hw_revision
        ) = pk_version = nos_version = cpu = uptime = total_memory = free_memory = None
        for line in dsSlots.split("\r\n"):
            # libLogger.error(line)
            if (
                "----------------------------------------------------" in line
            ):  # ne intereseasa outputul de dupa a doua linie cu "------"
                dashline += 1
                continue
            else:
                dashline += 1
                if (
                    "Info" in line
                    and "SysInfo" not in line
                    and "status niu" not in line
                ):
                    nameList = line.split("|")
                    # libLogger.info(nameList)
                    if len(nameList) == 3:
                        resultwords = [
                            word
                            for word in nameList[1].split()
                            if word.lower() not in ["system", "info"]
                        ]
                        name = " ".join(resultwords).replace(" ", "_").strip()
                    continue
                elif "Model" in line:
                    model = line.split(":")[1].strip()
                    continue
                elif "Serial" in line:
                    serial = line.split(":")[1].strip()
                    continue
                elif "H/W" in line:
                    hw_revision = line.split(":")[1].strip()
                    continue
                elif "NOS" in line:
                    nos_version = line.split(":")[1].strip()
                    continue
                elif "Package" in line:
                    pk_version = line.split(":")[1].strip()
                    continue
                elif "CPU" in line:
                    cpu = line.split(":", 1)[1].strip()
                    continue
                elif "UPTIME" in line:
                    uptime = line.split(":")[1].strip()
                    continue
                elif "MemTotal" in line:
                    if "SIU" in name:
                        total_memory = (
                            line.split(":")[1].replace("MemTotal", "").strip()
                        )
                    elif "SFU" in name:
                        total_memory = line.split(":")[2].strip()
                    continue
                elif "MemFree" in line:
                    if "SIU" in name:
                        free_memory = line.split(":")[1].replace("MemFree", "").strip()
                    elif "SFU" in name:
                        free_memory = line.split(":")[2].strip()
                    if name is not None:
                        libLogger.info(name)
                        dbSlot = OLTSlots.query.filter(
                            OLTSlots.name == name,
                            OLTSlots.olt_id == olt.id,
                        ).first()
                        if not dbSlot:
                            dbSlot = OLTSlots(name=name, olt_id=olt.id)
                        dbSlot.serial = serial
                        dbSlot.name = name
                        dbSlot.model = model
                        dbSlot.hw_revision = hw_revision
                        dbSlot.pk_version = pk_version
                        dbSlot.nos_version = nos_version
                        dbSlot.uptime = uptime
                        dbSlot.cpu = cpu
                        dbSlot.free_memory = free_memory
                        dbSlot.total_memory = total_memory
                        try:
                            db.session.add(dbSlot)
                        except Exception as e:
                            db.session.rollback()
                            libLogger.exception(f"Error is:\n{e}")

                        dbSlot = (
                            name
                        ) = (
                            model
                        ) = (
                            serial
                        ) = (
                            hw_revision
                        ) = (
                            pk_version
                        ) = (
                            nos_version
                        ) = cpu = uptime = total_memory = free_memory = None
                    continue
                elif "Planned Card" in line:
                    model = line.split(":")[1].strip()
                    if "NO CARD TYPE" in model:
                        model = None
                        name = None
                    if name is not None:
                        dbSlot = OLTSlots.query.filter(
                            OLTSlots.name == name,
                            OLTSlots.olt_id == olt.id,
                        ).first()
                        if not dbSlot:
                            dbSlot = OLTSlots(name=name, olt_id=olt.id)
                        dbSlot.name = name
                        dbSlot.model = model
                        try:
                            db.session.add(dbSlot)
                        except Exception as e:
                            db.session.rollback()
                            libLogger.exception(f"Error is:\n{e}")
                        dbSlot = (
                            name
                        ) = (
                            model
                        ) = (
                            serial
                        ) = (
                            hw_revision
                        ) = (
                            pk_version
                        ) = (
                            nos_version
                        ) = cpu = uptime = total_memory = free_memory = None
                    continue
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            libLogger.exception(f"Error is:\n{e}")
        updateTask(task.id, "Se scriu informatiile in baza de date", progress=89)
        db.session.commit()
        updateTask(
            task.id,
            "Toate datele au fost colectate fara erori",
            progress=100,
            finish=True,
        )
        libLogger.info("Task completed")
    except Exception as e:
        updateTask(
            task.id,
            "Eroare la citirea informatiilor de pe olt",
            progress=100,
            status="error",
            finish=True,
        )
        libLogger.error(f"Unhandled exception: {e}")
        libLogger.debug(traceback.format_exc())


def import_dba_profiles(olt, data):
    job = get_current_job()
    task = Task(
        id=job.get_id(),
        name="import_dba_profiles",
        description=f"import dba profiles from olt {olt.hostname}",
        username=data["username"],
    )
    db.session.add(task)
    db.session.commit()
    try:
        libLogger.info("Starting import dba profiles task")
        updateTask(task.id, "Se preiau informatii despre DBA-uri")
        ds = DasanReader(olt)
        if not ds.telnetConnect():
            updateTask(
                task.id,
                "Eroare la conectarea pe olt",
                progress=100,
                status="error",
                finish=True,
            )
            libLogger.error(f"Eroare la conectarea pe olt")
            return return_error("Eroare la conectarea pe olt", 400)
        dbapfs = ds.readDbaProfiles()
        libLogger.debug(dbapfs)
        for line in dbapfs.split("\r\n"):
            if "Profile Name" in line:
                dba_name = line.split(":")[-1].strip()
                DBA = DBAProfiles.query.filter(
                    DBAProfiles.name == dba_name, DBAProfiles.olt_id == olt.id
                ).first()
                if not DBA:
                    DBA = DBAProfiles(name=dba_name)
                    DBA.olt_id = olt.id
            if "SR DBA" in line or "Fixed |" in line or "NSR DBA" in line:
                DBA.mode = line.split("|")[0].strip()
                dba_fixed = line.split("|")[1].strip()
                if dba_fixed != "-":
                    DBA.fixed = dba_fixed
                dba_maximum = line.split("|")[2].strip()
                if dba_maximum != "-":
                    DBA.maximum = dba_maximum
                dba_assured = line.split("|")[3].strip()
                if dba_assured != "-":
                    DBA.assured = dba_assured
                db.session.add(DBA)
        updateTask(task.id, "Se scriu informatiile in baza de date", progress=89)
        db.session.commit()
        updateTask(
            task.id,
            "Toate datele au fost colectate fara erori",
            progress=100,
            finish=True,
        )
        libLogger.info("Task completed")
    except Exception as e:
        updateTask(
            task.id,
            "Eroare la citirea informatiilor de pe olt",
            progress=100,
            status="error",
            finish=True,
        )
        libLogger.error(f"Unhandled exception: {e}")
        libLogger.debug(traceback.format_exc())


def import_voip_profiles(olt, data):
    job = get_current_job()
    task = Task(
        id=job.get_id(),
        name="import_voip_profiles",
        description=f"import voip profiles from olt {olt.hostname}",
        username=data["username"],
    )
    db.session.add(task)
    db.session.commit()
    try:
        libLogger.info("Starting import voip profiles task")
        ds = DasanReader(olt)
        updateTask(task.id, "Se preiau informatii despre VOIP-uri")
        if not ds.telnetConnect():
            updateTask(
                task.id,
                "Eroare la conectarea pe olt",
                progress=100,
                status="error",
                finish=True,
            )
            libLogger.error(f"Eroare la conectarea pe olt")
            return return_error("Eroare la conectarea pe olt", 400)
        voippfs = ds.readVoipProfiles()
        libLogger.debug(voippfs)
        for line in voippfs.split("\r\n"):
            if "## VoIP Profile Description" in line:
                voip_name = line.split("(")[-1].strip(") ")
                VOIPP = VoipProfiles.query.filter(
                    VoipProfiles.name == voip_name, VoipProfiles.olt_id == olt.id
                ).first()
                if not VOIPP:
                    VOIPP = VoipProfiles(name=voip_name)
                    VOIPP.olt_id = olt.id
            if "Proxy server address" in line:
                VOIPP.proxy_server = line.split(":")[-1].strip()
            if "SIP registrar" in line:
                VOIPP.server = line.split(":")[-1].strip()
                db.session.add(VOIPP)
        updateTask(task.id, "Se scriu informatiile in baza de date", progress=89)
        db.session.commit()
        updateTask(
            task.id,
            "Toate datele au fost colectate fara erori",
            progress=100,
            finish=True,
        )
        libLogger.info("Task completed")
    except Exception as e:
        updateTask(
            task.id,
            "Eroare la citirea informatiilor de pe olt",
            progress=100,
            status="error",
            finish=True,
        )
        libLogger.error(f"Unhandled exception: {e}")
        libLogger.debug(traceback.format_exc())


def import_vlans(olt, data):
    job = get_current_job()
    task = Task(
        id=job.get_id(),
        name="import_vlans",
        description=f"import vlans from olt {olt.hostname}",
        username=data["username"],
    )
    db.session.add(task)
    db.session.commit()
    try:
        libLogger.info("Starting import vlans task")
        updateTask(task.id, " Se preiau informatii generale despre VLAN-uri")
        ds = DasanReader(olt)
        if not ds.telnetConnect():
            updateTask(
                task.id,
                "Eroare la conectarea pe olt",
                progress=100,
                status="error",
                finish=True,
            )
            libLogger.error(f"Eroare la conectarea pe olt")
            return return_error("Eroare la conectarea pe olt", 400)
        vlans_output = ds.readVlans()
        libLogger.debug(vlans_output)
        dashline = 0
        for line in vlans_output.split("\r\n"):
            if (
                "----------------------------------------------------" in line
            ):  # ne intereseasa outputul de dupa a doua linie cu "------"
                dashline += 1
                continue
            if (
                dashline == 2 and "#" not in line
            ):  # ne intereseasa outputul de dupa a doua linie cu "------" dar si fara ultima care este promptul
                vlan_name = line.split("|")[0].split("(")[0].strip()
                vid = line.split("|")[0].split("(")[-1]
                VLAN = OLTVlans.query.filter(
                    OLTVlans.vid == vid, OLTVlans.olt_id == olt.id
                ).first()
                if not VLAN:
                    VLAN = OLTVlans(olt_id=olt.id, name=vlan_name, vid=vid, cos="3")
                else:
                    VLAN.name = vlan_name
                    VLAN.vid = vid
                    VLAN.cos = 3
                db.session.add(VLAN)
        updateTask(task.id, "Se scriu informatiile in baza de date", progress=89)
        db.session.commit()
        updateTask(
            task.id,
            "Toate datele au fost colectate fara erori",
            progress=100,
            finish=True,
        )
        libLogger.info("Task completed")
    except Exception as e:
        updateTask(
            task.id,
            "Eroare la citirea informatiilor de pe olt",
            progress=100,
            status="error",
            finish=True,
        )
        libLogger.error(f"Unhandled exception: {e}")
        libLogger.debug(traceback.format_exc())


def import_traffic_profiles(olt, data):
    job = get_current_job()
    task = Task(
        id=job.get_id(),
        name="import_traffic_profiles",
        description=f"import traffic profiles from olt {olt.hostname}",
        username=data["username"],
    )
    db.session.add(task)
    db.session.commit()
    try:
        libLogger.info("Starting import traffic profiles task")
        updateTask(task.id, "Se preiau informatii despre Traffic Profiles")
        ds = DasanReader(olt)
        if not ds.telnetConnect():
            updateTask(
                task.id,
                "Eroare la conectarea pe olt",
                progress=100,
                status="error",
                finish=True,
            )
            libLogger.error(f"Eroare la conectarea pe olt")
            return return_error("Eroare la conectarea pe olt", 400)
        tp_output = ds.readTrafficProfiles()
        libLogger.debug(tp_output)
        updateTask(task.id, "S-au citit informatiile de pe OLT", progress=20)
        traffic_profiles_dict = {}
        uni_mode = False
        limited_tp_details = False
        for line in tp_output.split("\r\n"):
            if "show traffic-profile | i" in line:
                continue
            if "## Traffic Profile Description" in line:
                tp_name = line.split("(")[1].strip(") ")
                traffic_profiles_dict[tp_name] = {
                    "tp_name": tp_name,
                    "services": {},
                    "voip_profile": None,
                    "ports_mode": {},
                }
                uni_mode = False
            if "## Traffic Profile Description" in line and "H665GR_VLAN" in line:
                limited_tp_details = True
            if "## Traffic Profile Description" in line and "H665GR_VLAN" not in line:
                limited_tp_details = False
            # libLogger.info(f"procesing line: {line}")
            if not uni_mode:
                if "T-CONT index" in line:
                    service_idx = line.split()[2]
                    traffic_profiles_dict[tp_name]["services"][service_idx] = {
                        "port_list": []
                    }
                elif "DBA profile name" in line:
                    dba_name = line.split(":")[-1].strip()
                    traffic_profiles_dict[tp_name]["services"][service_idx][
                        "DBA"
                    ] = dba_name
                elif re.match(r".*bridge \d is configured", line):
                    service_idx = line.split()[1]
                elif re.match(".*IP host config \d is configured", line):
                    service_idx = line.split()[3]
                elif "VID List" in line:
                    vlan_list = line.split(":")[1].split("(")[0].strip()
                    traffic_profiles_dict[tp_name]["services"][service_idx][
                        "vlan_list"
                    ] = str(vlan_list)
                elif re.match(r"   (UNI|Virtual Ethernet) (\d) is configured $", line):
                    # port = line.split("is configured")[0].strip().replace("UNI", "eth")
                    port = re.match(
                        r"   (UNI|Virtual Ethernet) (\d) is configured $", line
                    ).group(2)
                    port = "eth " + port  # ??? h665GR are Virtual eth ???
                    traffic_profiles_dict[tp_name]["services"][service_idx][
                        "port_list"
                    ].append(port)
                elif "Ext-Vlan-Tagging-Oper" in line:
                    if "H665GR" in tp_name:
                        if not limited_tp_details:
                            evto = tp_name.split("-")[1].split("+")[0].strip("VID")
                        else:
                            evto = "0"
                        traffic_profiles_dict[tp_name]["ports_mode"][port] = {
                            "mgmt_mode": "Non-OMCI",
                            "nat": 1 if "NAT" in tp_name else 0,
                        }
                    else:
                        evto = line.split(":")[-1].strip(" VID").strip("t")
                    traffic_profiles_dict[tp_name]["services"][service_idx][
                        "evto"
                    ] = evto
                elif "IP Address Type" in line:
                    ip_type = line.split(":")[-1].strip()
                    traffic_profiles_dict[tp_name]["services"][service_idx][
                        "ip_type"
                    ] = ip_type
                elif "VoIP Profile Name" in line:
                    vp_name = line.split(":")[-1].strip()
                    traffic_profiles_dict[tp_name]["voip_profile"] = vp_name
                elif "Slot 1(eth) is configured." in line:
                    uni_mode = True

            else:
                if re.match("   UNI .* is configured $", line):
                    port = line.split("is configured")[0].strip().replace("UNI", "eth")
                elif "Port Mgmt Mode" in line:
                    mgmt_mode = line.split(":")[-1].strip()
                    traffic_profiles_dict[tp_name]["ports_mode"][port] = {
                        "mgmt_mode": mgmt_mode,
                        "nat": 1 if mgmt_mode == "Non-OMCI" else 0,
                    }

        for t in traffic_profiles_dict:
            if traffic_profiles_dict[t]["voip_profile"] is not None:
                traffic_profiles_dict[t]["voip_vlan"] = t.split("VOIP")[1].split("+")[0]
        libLogger.debug(traffic_profiles_dict)
        updateTask(
            task.id,
            f"Au fost identificate {len(traffic_profiles_dict)} profile de trafic",
            progress=30,
        )
        for t in traffic_profiles_dict:
            TP = DasanTrafficProfiles.query.filter(
                DasanTrafficProfiles.olt_id == olt.id, DasanTrafficProfiles.name == t
            ).first()
            if not TP:
                TP = DasanTrafficProfiles(olt_id=olt.id, name=t)
            if traffic_profiles_dict[t]["voip_profile"]:
                VP = VoipProfiles.query.filter(
                    VoipProfiles.olt_id == olt.id,
                    VoipProfiles.name == traffic_profiles_dict[t]["voip_profile"],
                ).first()
                if VP:
                    TP.voip_profile_id = VP.id
                    TP.voip_vlan = traffic_profiles_dict[t]["voip_vlan"]
                else:
                    libLogger.warning(
                        f"Voip profile {traffic_profiles_dict[t]['voip_profile']} of traffic-profile {t} was not found in db"
                    )
            db.session.add(TP)
            for s in traffic_profiles_dict[t]["services"]:
                SP = DasanTPServices.query.filter(
                    DasanTPServices.dasan_traffic_profile_id == TP.id,
                    DasanTPServices.service_id == s,
                ).first()
                if not SP:
                    SP = DasanTPServices(dasan_traffic_profile_id=TP.id, service_id=s)
                try:
                    DBAP = DBAProfiles.query.filter(
                        DBAProfiles.olt_id == olt.id,
                        DBAProfiles.name
                        == traffic_profiles_dict[t]["services"][s]["DBA"],
                    ).first()
                except:
                    libLogger.warning(
                        f"Service without DBA: {t} - {s} {traffic_profiles_dict[t]['services'][s]}"
                    )
                if DBAP:
                    SP.dba_id = DBAP.id
                if "ip_type" in traffic_profiles_dict[t]["services"][s].keys():
                    SP.ip_type = (
                        0
                        if traffic_profiles_dict[t]["services"][s]["ip_type"]
                        == "Static"
                        else 1
                    )
                db.session.add(SP)
                for pp in traffic_profiles_dict[t]["services"][s]["port_list"]:
                    DTPP = DasanTPPorts.query.filter(
                        DasanTPPorts.dasan_tp_services_id == SP.id,
                        DasanTPPorts.port == pp,
                    ).first()
                    if not DTPP:
                        DTPP = DasanTPPorts(dasan_tp_services_id=SP.id, port=pp)
                    if pp in traffic_profiles_dict[t]["ports_mode"].keys():
                        DTPP.mgmt_mode = traffic_profiles_dict[t]["ports_mode"][pp][
                            "mgmt_mode"
                        ]
                        DTPP.nat = traffic_profiles_dict[t]["ports_mode"][pp]["nat"]
                    db.session.add(DTPP)
                if "vlan_list" in traffic_profiles_dict[t]["services"][s].keys():
                    vl_list = traffic_profiles_dict[t]["services"][s]["vlan_list"]
                    if len(vl_list) > 0:
                        vl_list = range_expand(vl_list)
                        for v in vl_list:
                            VV = DasanTPVlans.query.filter(
                                DasanTPVlans.dasan_tp_services_id == SP.id,
                                DasanTPVlans.vid == v,
                            ).first()
                            if not VV:
                                VV = DasanTPVlans(
                                    dasan_tp_services_id=SP.id, vid=v, tag=True
                                )
                            db.session.add(VV)
                elif "evto" in traffic_profiles_dict[t]["services"][s].keys():
                    evto = re.sub(
                        "\D", "", traffic_profiles_dict[t]["services"][s]["evto"]
                    )  # pastram doar cifrele din denumirea evto
                    if len(evto) > 0:
                        EV = DasanTPVlans.query.filter(
                            DasanTPVlans.dasan_tp_services_id == SP.id,
                            DasanTPVlans.vid == evto,
                        ).first()
                        if not EV:
                            EV = DasanTPVlans(
                                dasan_tp_services_id=SP.id, vid=evto, tag=False
                            )
                        db.session.add(EV)
            db.session.commit()
        updateTask(task.id, "Se scriu informatiile in baza de date", progress=89)
        try:
            db.session.commit()
            updateTask(
                task.id,
                "Toate datele au fost colectate fara erori",
                progress=100,
                finish=True,
            )
            libLogger.info("Task completed")
        except Exception as e:
            libLogger.error(f"Import traffic-profiles: Error saving to db. {e}")
            libLogger.debug(traceback.format_exc())
            updateTask(
                task.id,
                "Eroare la salvarea profilelor de trafic in baza de date",
                status="error",
                finish=True,
            )
    except Exception as e:
        libLogger.error(f"Unhandled exception. {e}")
        libLogger.debug(traceback.format_exc())
        updateTask(
            task.id,
            "Eroare necunoscuta la import traffic profiles",
            status="error",
            finish=True,
        )


def import_onu_profiles(olt, data):
    job = get_current_job()
    task = Task(
        id=job.get_id(),
        name="import_onu_profiles",
        description=f"import onu profiles from olt {olt.hostname}",
        username=data["username"],
    )
    db.session.add(task)
    db.session.commit()
    try:
        libLogger.info("Starting import onu profiles task")
        ds = DasanReader(olt)
        if not ds.telnetConnect():
            updateTask(
                task.id,
                "Eroare la conectarea pe olt",
                progress=100,
                status="error",
                finish=True,
            )
            libLogger.error(f"Eroare la conectarea pe olt")
            return return_error("Eroare la conectarea pe olt", 400)
        onu_p_output = ds.ReadONTProfiles()
        libLogger.debug(onu_p_output)
        for line in onu_p_output.split("\r\n"):
            if "## ONU Profile Description" in line:
                onu_p_name = line.split("(")[-1].strip(") ")
                DOP = DasanONTProfiles.query.filter(
                    DasanONTProfiles.name == onu_p_name,
                    DasanONTProfiles.olt_id == olt.id,
                ).first()
                if not DOP:
                    DOP = DasanONTProfiles(olt_id=olt.id, name=onu_p_name)
            if "Traffic Profile" in line:
                tp_name = line.split(":")[-1].strip()
                TP = DasanTrafficProfiles.query.filter(
                    DasanTrafficProfiles.olt_id == olt.id,
                    DasanTrafficProfiles.name == tp_name,
                ).first()
                if TP:
                    DOP.dasan_traffic_profile_id = TP.id
                    db.session.add(DOP)
                else:
                    libLogger.warning(
                        f">>> TP not found for this onu-profile >>> {onu_p_name} -- {tp_name} -- {TP}"
                    )
        updateTask(task.id, "Se scriu informatiile in baza de date", progress=89)
        db.session.commit()
        updateTask(
            task.id,
            "Toate datele au fost colectate fara erori",
            progress=100,
            finish=True,
        )
        libLogger.info("Task completed")
    except Exception as e:
        task.status = "error"
        libLogger.error("Unhandled exception", e)


def get_unconfigured_onts(olt, username):
    job = get_current_job()
    task = Task(
        id=job.get_id(),
        name="get_unconfigured_onts",
        description=f"getting unconfigured onts for olt {olt.hostname}",
        username=username,
    )
    db.session.add(task)
    db.session.commit()

    libLogger.debug(f"Starting {task.name} task")
    updateTask(
        task.id,
        f"Task-ul de autofind a inceput!",
        progress=10,
        status="info",
        finish=False,
    )

    ds = DasanReader(olt)

    updateTask(
        task.id,
        f"Se incepe conectarea prin snmp si citirea ont-urilor",
        progress=40,
        status="error",
        finish=False,
    )
    onts_set_from_snmp = ds.ReadONTsSNMP_serial()
    if not onts_set_from_snmp:
        updateTask(
            task.id,
            f"Nu am putut sa ne conectam prin snmp la olt-ul cu id-ul {olt.id}, se abandoneaza..",
            progress=100,
            status="error",
            finish=True,
        )
        libLogger.error(f"Could not connect trough snmp at OLT with id: {olt.id}")
        return return_error(
            f"Could not connect trough snmp at OLT with id: {olt.id}", 400
        )

    unprepared_query = """ 
    SELECT interfaces.ifIndex, onts.ont_id , onts.sn
    from onts
    inner join interfaces
    on onts.interface_id=interfaces.id
    where onts.olt_id = :olt_id ORDER BY onts.id;
    """
    myresult = db.session.execute(unprepared_query, {"olt_id": olt.id})
    onts_set_from_db = set()
    for x in myresult:
        onts_set_from_db.add((str(x[0]), str(x[1]), x[2]))

    if len(onts_set_from_snmp.difference(onts_set_from_db)):
        libLogger.debug(
            f"Total unconfigured onts to add from snmp: {len(onts_set_from_snmp.difference(onts_set_from_db))}"
        )
        updateTask(
            task.id,
            f"Au fost gasite {len(onts_set_from_snmp.difference(onts_set_from_db))} ont-uri neconfigurate"
            + "se adauga in baza de date..",
            progress=60,
            status="info",
            finish=False,
        )
        for unconfigured_ont in onts_set_from_snmp.difference(onts_set_from_db):
            ont_model_from_snmp = ds.ReadONTSNMP_model(
                unconfigured_ont[0], unconfigured_ont[1]
            )

            ont_deviceModel_id = (
                DeviceModel.query.filter(DeviceModel.model == ont_model_from_snmp)
                .first()
                .id
            )

            if not ont_deviceModel_id:
                libLogger.warning(
                    f"DeviceModel {ont_model_from_snmp} doesn't exist in the database, creating.."
                )
                new_deviceModel = DeviceModel(
                    model=ont_model_from_snmp,
                    vendor="dasan",
                    device_type="ont",
                )
                db.session.add(new_deviceModel)

            libLogger.debug(
                f"Going to add ont with:\ninterface id -> {unconfigured_ont[0]}"
                + f"\nont id -> {unconfigured_ont[1]}"
                + f"\nsn -> {unconfigured_ont[2]}"
                + f"\nmodel -> {ont_model_from_snmp} with id -> {ont_deviceModel_id}"
            )
            ont = ONT(
                olt_id=olt.id,
                ont_id=unconfigured_ont[1],
                sn=unconfigured_ont[2],
                interface_id=unconfigured_ont[0],
                device_model_id=ont_deviceModel_id,
                sync_status="Neconfigurat",
                last_update=datetime.datetime.now(),
            )
            db.session.add(ont)

        commit_result = safe_commit(
            success_msg=f"Successfully saved onts into database",
            success_code=200,
            error_msg=f"Failed to save onts into database",
            error_code=417,
        )

        if commit_result[1] == 200:
            libLogger.debug(commit_result[0])
            updateTask(
                task.id,
                "ONT-urile gasit au fost salvate in baza de date cu success !",
                status="info",
                finish=True,
                progress=100,
            )

            return return_success(commit_result[0], 200)
        else:
            libLogger.error(commit_result[0])
            updateTask(
                task.id,
                "ONT-urile gasite nu au putut fi salvate in baza de date..",
                status="error",
                finish=True,
                progress=100,
            )
            return return_error(commit_result[0], 404)
    else:
        libLogger.debug(f"No unconfigured onts have been found trough snmp")
        updateTask(
            task.id,
            "Nu au fost gasite ont-uri noi la autofind",
            status="info",
            finish=True,
            progress=100,
        )
        return return_success("Nu au fost gasite ont-uri noi la autofind", 200)


def import_onts(olt, data):
    try:
        job = get_current_job()
        task = Task(
            id=job.get_id(),
            name="import_onts",
            description=f"import onts from olt {olt.hostname}",
            username=data["username"],
        )
        db.session.add(task)
        db.session.commit()
        libLogger.info("Starting import onts task")
        ds = DasanReader(olt)
        if not ds.telnetConnect():
            updateTask(
                task.id,
                "Eroare la conectarea pe olt",
                progress=100,
                status="error",
                finish=True,
            )
            libLogger.error(f"Eroare la conectarea pe olt")
            return return_error("Eroare la conectarea pe olt", 400)
        onts_output = ds.ReadONTs()
        libLogger.debug(onts_output)
        all_interfaces = Interfaces.query.filter_by(olt_id=olt.id).all()
        valid_onu = False
        # verificam intai daca exista in db toate modele de ont-uri
        all_models = set()
        for line in onts_output.split("\r\n"):
            if "show onu detail-info" in line:
                continue
            if "Model Name" in line:
                all_models.add(line.split(":")[1].strip())
        unkown_model = "unknown_onu_model"
        for m in all_models:
            if m == "":
                m = unkown_model
            DM = DeviceModel.query.filter(DeviceModel.model == m).first()
            if not DM:
                DM = DeviceModel(model=m, vendor="dasan", device_type="ont")
                db.session.add(DM)
                try:
                    db.session.commit()
                except Exception as e:
                    libLogger.exception(f" failled to add device model {m} to database")
                    db.session.rollback()
        for line in onts_output.split("\r\n"):
            libLogger.debug(f"processing line:  {line}")
            if "show onu detail-info" in line:
                continue
            try:
                if "OLT :" in line:
                    interface_short = line.split(",")[0].split(":")[1].strip()
                    valid_onu = True
                    for i in all_interfaces:
                        if interface_short in i.ifDescr:
                            IFX = i
                            break
                    ont_id = line.split(",")[1].split(":")[1]
                    libLogger.debug(f"processing onu:  {interface_short} {ont_id}")
                    ONU = ONT.query.filter(
                        ONT.olt_id == olt.id,
                        ONT.interface_id == IFX.id,
                        ONT.ont_id == ont_id,
                    ).first()
                    if not ONU:
                        ONU = ONT(olt_id=olt.id, ont_id=ont_id)
                    try:
                        libLogger.debug(
                            f"set onu.interface_id {IFX.id}  - interface {interface_short} - {IFX.ifDescr}"
                        )
                        ONU.interface_id = IFX.id
                    except UnboundLocalError:
                        libLogger.error(
                            f"Interface {interface_short} not found in DB. Cannot add ont if interface is unknown"
                        )
                        valid_onu = False
                if "Activation Status" in line and valid_onu:
                    # invalid(0), inactive(1), active(2), running(3), activePending(4), deactivePending(5), disablePending(6), disable(7), unknown(255)
                    status_map = {
                        "invalid": 0,
                        "inactive": 1,
                        "active": 2,
                        "running": 3,
                        "activePending": 4,
                        "deactivePending": 5,
                        "disablePending": 6,
                        "disable": 7,
                        "unknown": 255,
                    }
                    ONU.status = status_map[line.split(":")[1].strip().lower()]
                    libLogger.debug(f"set onu.status:  {ONU.status} ")
                if "Serial Number" in line and valid_onu:
                    ONU.sn = line.split(":")[1].strip()
                    libLogger.debug(f"set onu.sn:  {ONU.sn} ")
                if "Description" in line and valid_onu:
                    ONU.description = line.split(":")[1].strip()
                    libLogger.debug(f"set onu.description:  {ONU.description} ")
                if "Model Name" in line and valid_onu:
                    mn = line.split(":")[1].strip()
                    if mn == "":
                        mn = unkown_model
                    DM = DeviceModel.query.filter(DeviceModel.model == mn).first()
                    libLogger.debug(f"set onu.model:  {ONU.device_model_id} ")
                    ONU.device_model_id = DM.id
                if "MAC Address" in line and valid_onu:
                    ONU.mac = line.split()[-1].strip()
                    libLogger.debug(f"set onu.mac:  {ONU.mac} ")
                if "onu-profile" in line and valid_onu:
                    op_name = line.split(":")[1].strip()
                    if len(op_name) > 1:
                        OP = DasanONTProfiles.query.filter(
                            DasanONTProfiles.olt_id == olt.id,
                            DasanONTProfiles.name == op_name,
                        ).first()
                        if not OP:
                            libLogger.error(
                                f"Cannot find ONU Profile {op_name} in database. Ensure ONU Profiles are imported before"
                            )
                            valid_onu = False
                        ONU.dasan_ont_profile_id = OP.id
                    libLogger.debug(
                        f"set onu.dasan_ont_profile_id:  {ONU.dasan_ont_profile_id} "
                    )
                    db.session.add(
                        ONU
                    )  # onu profile line trebuie sa fie ultima linie de interes
                    libLogger.debug(f"onu added to session:  {ONU.sn}")
            except Exception as e:
                libLogger.exception(f"Exception on line: {line} \n {e}")
        try:
            db.session.commit()
            libLogger.debug("import onts commited succesfuly")
        except Exception as e:
            libLogger.exception(
                f"Error on db.session.commit when importing onts.\nError is:\n{e}"
            )
            db.session.rollback()
        updateTask(task.id, "Se scriu informatiile in baza de date", progress=89)
        db.session.commit()
        updateTask(
            task.id,
            "Toate datele au fost colectate fara erori",
            progress=100,
            finish=True,
        )
        libLogger.info("Task completed")
    except Exception as e:
        updateTask(
            task.id,
            "Eroare la citirea informatiilor de pe olt",
            progress=100,
            status="error",
            finish=True,
        )
        libLogger.error(f"Unhandled exception: {e}")
        libLogger.debug(traceback.format_exc())


def import_ont_configs(olt, username):
    job = get_current_job()
    task = Task(
        id=job.get_id(),
        olt_id=olt.id,
        name="import_all_onts_configs",
        description=f"import all onts configs from olt",
        status="waiting",
        username=username,
    )
    libLogger.info("Starting refresh ont task")
    db.session.add(task)
    db.session.commit()
    updateTask(
        task.id,
        f"Se citesc toate ont-urile de pe {olt.hostname} din baza de date ",
        progress=5,
    )
    onts = ONT.query.filter_by(olt_id=olt.id).all()
    updateTask(
        task.id,
        f"Se preiau informatii despre ont-urile de pe {olt.hostname}",
        progress=10,
    )
    all_olt_nets = IPPool.query.filter_by(olt_id=olt.id).all()
    for ont in onts:
        libLogger.debug(f"Procesing ont: {marshal(ont, _ont)}")
        interface = Interfaces.query.filter_by(id=ont.interface_id).first()
        try:
            ds = DasanReader(olt)
            conf = ds.ReadONTConfig(ont, interface)
            if not conf:
                updateTask(
                    task.id,
                    f"Eroare generica la citirea datelor prin SNMP pentru ont-ul {ont.sn}",
                    status="ERROR",
                )
            if conf["sn"] == "NOSUCHINSTANCE":
                libLogger.warning(
                    f"ONT-ul {ont.sn} din baza de date nu exista pe olt {olt.hostname}"
                )
                continue
            ont.sn = conf["sn"]
            ont.description = conf["description"]
            ont.firmware = conf["firmware"]
            if "mac" in conf.keys():
                ont.mac = conf["mac"]
            if "username" in conf.keys():
                ont.username = conf["username"]
            if "password" in conf.keys():
                ont.password = conf["password"]
            ont.status = conf["status"]
            # Checking for optical rx power in here
            if "oltrxpower" in conf.keys():
                ont.oltrxpower = conf["oltrxpower"]
            if "rxpower" in conf.keys():
                ont.rxpower = conf["rxpower"]

            OP = DasanONTProfiles.query.filter_by(name=conf["onu_profile"]).first()
            if OP:
                ont.dasan_ont_profile_id = OP.id
            else:
                libLogger.warning(
                    f"Cannot find this onu profile ( {conf['onu_profile']} ) in database"
                )
            ont.last_update = datetime.datetime.now()
            db.session.add(ont)
            job.meta["progress"] = 33
            job.save_meta()
        except Exception as e:
            libLogger.error(
                f"Error reading some data for ont {ont.sn}. Error: {str(e)}"
            )
            libLogger.debug(traceback.format_exc())
        # save catv status
        try:
            if "video" in conf.keys():
                OTV = ONTCATV.query.filter_by(ont_id=ont.id).first()
                if OTV:
                    OTV.admin_status = conf["video"]["admin_status"]
                    OTV.oper_status = conf["video"]["oper_status"]
                    OTV.optical_rx = conf["video"]["optical_rx"]
                    OTV.rf_tx = conf["video"]["rf_tx"]
                else:
                    new_catv = ONTCATV(
                        ont_id=ont.id,
                        admin_status=conf["video"]["admin_status"],
                        oper_status=conf["video"]["oper_status"],
                        optical_rx=conf["video"]["optical_rx"],
                        rf_tx=conf["video"]["rf_tx"],
                    )
                    db.session.add(new_catv)
        except Exception as e:
            libLogger.exception(e)
        # save voip status
        try:
            for i in conf["voip"]["nr"]:
                OV = ONTVoip.query.filter_by(phone_number=i).first()
                lidx = conf["voip"]["nr"].index(i)
                if not OV:
                    OV = ONTVoip(
                        ont_id=ont.id,
                        admin_status=conf["voip"]["status"][lidx + 1],
                        pots=lidx + 1,
                        phone_number=i,
                        password=conf["voip"]["auth"][lidx],
                    )
                else:
                    OV.password = conf["voip"]["auth"][lidx]
                db.session.add(OV)
            job.meta["progress"] = 66
            job.save_meta()
        except Exception as e:
            libLogger.error(e)

        # save ip address of ip-host1
        if conf["ip-host-ips"]:
            ip_h1 = ipaddress.ip_address(conf["ip-host-ips"][0])
            if ip_h1 != "0.0.0.0":
                for nw in all_olt_nets:
                    if ip_h1 in ipaddress.ip_network(nw.network):
                        new_ip = IPAddress(
                            ip_pool_id=nw.id,
                            ont_id=ont.id,
                            ip=str(ip_h1),
                        )
                        db.session.add(new_ip)
        db.session.commit()
        ds.telnetDisconnect()
    updateTask(task.id, "Toate datele au fost colectate", progress=100, finish=True)
    db.session.commit()
    libLogger.info("Task completed")


def delete_unused_traffic_profiles_task(unused_traffic_profiles, username):
    job = get_current_job()
    olt = OLT.query.filter_by(id=unused_traffic_profiles[0].olt_id).first()
    if not olt:
        libLogger.warning(
            "Olt with id {unused_traffic_profiles[0].olt_id.id} has not been found in the db !"
        )

    libLogger.debug(f"We found olt in the db! Id: {olt.id}")
    task = Task(
        id=job.get_id(),
        olt_id=olt.id,
        name="delete_traffic_unused_profiles_task",
        description=f"Deleting unused traffic profiles",
        status="waiting",
        username=username,
    )
    db.session.add(task)
    db.session.commit()

    ds = DasanReader(olt)
    libLogger.debug(
        f"Se vor sterge {len(unused_traffic_profiles)} profile nefolosite de pe olt prin telnet"
    )
    updateTask(
        task.id,
        f"Se vor sterge {len(unused_traffic_profiles)} profile nefolosite de pe olt prin telnet",
        status="info",
        finish=False,
        progress=60,
    )

    used_found_profiles = set()
    unused_traffic_profiles = {profile.name for profile in unused_traffic_profiles}
    print(unused_traffic_profiles)

    for unused_profile in unused_traffic_profiles:
        deleted_successfully = True
        print(f"\n\nDeleting profile: {unused_profile}")
        libLogger.debug(f"Trying to delete from olt the profile {unused_profile}")
        delete_onu_profile_command = (
            f"conf t" + "\ngpon" + f"\nno traffic-profile {unused_profile}" + "\nend"
        )
        for line_of_command in delete_onu_profile_command.splitlines():
            libLogger.debug(f"Sending command: {line_of_command}")
            command_result = ds.sendtelnetCommand(line_of_command)
            if "No exist Entry" in command_result:
                libLogger.warning(
                    f"Numele de profil {unused_profile} nu a fost gasit pe olt !"
                )
                deleted_successfully = False
            if "is used by onu-profile" in command_result:
                libLogger.warning(
                    f"Profilul de traffic {unused_profile} apartine unui profil de ont !"
                )
                updateTask(
                    task.id,
                    f"Profilul de traffic {unused_profile} apartine unui profil de ont !",
                    status="error",
                    finish=False,
                    progress=60,
                )
                used_found_profiles.add(unused_profile)
                deleted_successfully = False
        if deleted_successfully:
            libLogger.debug(
                f"Deleted successfullly from olt the profile {unused_profile} !"
            )
        else:
            libLogger.warning(
                f"Failed to delete from olt the profile {unused_profile} !"
            )

    updateTask(
        task.id,
        f"Stergerea de pe olt s-a sfarsit, urmeaza din baza de date..",
        status="error",
        finish=False,
        progress=70,
    )

    libLogger.debug(
        f"A total of {len(used_found_profiles)} profiles has been found used by an ont"
    )
    successfully_deleted_profiles = 0
    failed_to_delete_profiles = 0
    # for profile_name in unused_onu_profiles.difference(used_found_profiles):
    for profile_name in unused_traffic_profiles.difference(used_found_profiles):
        libLogger.debug(f"Trying to delete from db the profile {profile_name}")
        traffic_profile = DasanTrafficProfiles.query.filter_by(
            name=profile_name
        ).first()

        if not traffic_profile:
            updateTask(
                task.id,
                f"Profilul {profile_name} nu a fost gasit in baza de date,"
                + "acest lucru necesita investigatii de catre dezvoltator..",
                status="error",
                finish=False,
                progress=70,
            )
            libLogger.error(
                f"Profilul {profile_name} nu a fost gasit in baza de date, "
            )
            continue

        db.session.delete(traffic_profile)
        commit_result = safe_commit(
            success_msg=f"Successfully deleted traffic profile {profile_name} from DB",
            success_code=200,
            error_msg=f"Failled to delete traffic profile {profile_name} from DB",
            error_code=417,
        )

        if commit_result[1] == 200:
            libLogger.debug(commit_result[0])
            successfully_deleted_profiles += 1
        else:
            db.session.rollback()
            failed_to_delete_profiles += 1
            libLogger.error(commit_result[0])
            updateTask(
                task.id,
                "Profilul de traffic NU a putut fi sters din baza de date!",
                status="error",
                finish=False,
                progress=70,
            )
    libLogger.debug(
        f"Stergerea a luat sfarsit, sumar:\n"
        + f"Profile de traffic sterse cu succes -> {successfully_deleted_profiles}\n"
        + f"Profile de traffic gasite pe olt ca fiind folosite de catre un profil de ont -> {len(used_found_profiles)}\n"
        + f"Profile de traffic ce nu au putut fi sterse din baza de date -> {failed_to_delete_profiles}\n"
    )
    updateTask(
        task.id,
        f"Stergerea a luat sfarsit, sumar:",
        status="info",
        finish=False,
        progress=97,
    )
    updateTask(
        task.id,
        f"Profile de traffic sterse cu succes -> {successfully_deleted_profiles}\n",
        status="info",
        finish=False,
        progress=98,
    )
    updateTask(
        task.id,
        f"Profile de traffic gasite pe olt ca fiind folosite de catre un profil de ont -> {len(used_found_profiles)}\n",
        status="info",
        finish=False,
        progress=99,
    )
    updateTask(
        task.id,
        f"Profile de traffic ce nu au putut fi sterse din baza de date -> {failed_to_delete_profiles}\n",
        status="info",
        finish=True,
        progress=100,
    )


def delete_unused_onu_profiles_task(unused_onu_profiles, username):
    job = get_current_job()
    olt = OLT.query.filter_by(id=unused_onu_profiles[0].olt_id).first()
    if not olt:
        libLogger.warning(
            "Olt with id {unused_onu_profiles[0].olt_id.id} has not been found in the db !"
        )

    libLogger.debug(f"We found olt in the db! Id: {olt.id}")
    task = Task(
        id=job.get_id(),
        olt_id=olt.id,
        name="delete_onu_unused_profiles_task",
        description=f"Deleting unused onu profiles",
        status="waiting",
        username=username,
    )
    db.session.add(task)
    db.session.commit()

    ds = DasanReader(olt)
    libLogger.debug(
        f"Se vor sterge {len(unused_onu_profiles)} profile nefolosite de pe olt prin telnet"
    )
    updateTask(
        task.id,
        f"Se vor sterge {len(unused_onu_profiles)} profile nefolosite de pe olt prin telnet",
        status="info",
        finish=False,
        progress=60,
    )

    used_found_profiles = set()
    unused_onu_profiles = {profile.name for profile in unused_onu_profiles}
    print(unused_onu_profiles)

    for unused_profile in unused_onu_profiles:
        deleted_successfully = True
        print(f"\n\nDeleting profile: {unused_profile}")
        libLogger.debug(f"Trying to delete from olt the profile {unused_profile}")
        delete_onu_profile_command = (
            f"conf t" + "\ngpon" + f"\nno onu-profile {unused_profile}" + "\nend"
        )
        print(f"Command: {delete_onu_profile_command}")
        for line_of_command in delete_onu_profile_command.splitlines():
            libLogger.debug(f"Sending command: {line_of_command}")
            command_result = ds.sendtelnetCommand(line_of_command)
            if "No exist Entry" in command_result:
                libLogger.warning(
                    f"Numele de profil {unused_profile} nu a fost gasit pe olt !"
                )
                deleted_successfully = False
            if "Applied profile to onu, can't delete" in command_result:
                libLogger.warning(
                    f"Profilul {unused_profile} are ont-uri asociate pe olt!"
                )
                updateTask(
                    task.id,
                    f"Profilul {unused_profile} are ont-uri asociate pe olt!",
                    status="error",
                    finish=False,
                    progress=60,
                )
                used_found_profiles.add(unused_profile)
                deleted_successfully = False
        if deleted_successfully:
            libLogger.debug(
                f"Deleted successfullly from olt the profile {unused_profile} !"
            )
        else:
            libLogger.warning(
                f"Failed to delete from olt the profile {unused_profile} !"
            )

    updateTask(
        task.id,
        f"Stergerea de pe olt s-a sfarsit, urmeaza din baza de date..",
        status="error",
        finish=False,
        progress=70,
    )

    libLogger.debug(
        f"A total of {len(used_found_profiles)} profiles has been found used by an ont"
    )
    successfully_deleted_profiles = 0
    failed_to_delete_profiles = 0
    for profile_name in unused_onu_profiles.difference(used_found_profiles):
        libLogger.debug(f"Trying to delete from db the profile {profile_name}")
        ont_profile = DasanONTProfiles.query.filter_by(name=profile_name).first()

        if not ont_profile:
            updateTask(
                task.id,
                f"Profilul {profile_name} nu a fost gasit in baza de date,"
                + "acest lucru necesita investigatii de catre dezvoltator..",
                status="error",
                finish=False,
                progress=70,
            )
            libLogger.error(
                f"Profilul {profile_name} nu a fost gasit in baza de date, "
            )
            continue

        db.session.delete(ont_profile)
        commit_result = safe_commit(
            success_msg=f"Successfully deleted onu profile {profile_name} from DB",
            success_code=200,
            error_msg=f"Failled to delete onu profile {profile_name} from DB",
            error_code=417,
        )

        if commit_result[1] == 200:
            libLogger.debug(commit_result[0])
            successfully_deleted_profiles += 1
        else:
            failed_to_delete_profiles += 1
            libLogger.error(commit_result[0])
            updateTask(
                task.id,
                "Profilul de ont NU a putut fi sters din baza de date!",
                status="error",
                finish=False,
                progress=70,
            )
    libLogger.debug(
        f"Stergerea a luat sfarsit, sumar:\n"
        + f"Profile sterse cu succes -> {successfully_deleted_profiles}\n"
        + f"Profile gasite pe olt ca fiind folosite de catre un ont -> {len(used_found_profiles)}\n"
        + f"Profile ce nu au putut fi sterse din baza de date -> {failed_to_delete_profiles}\n"
    )
    updateTask(
        task.id,
        f"Stergerea a luat sfarsit, sumar:",
        status="info",
        finish=False,
        progress=97,
    )
    updateTask(
        task.id,
        f"Profile sterse cu succes : {successfully_deleted_profiles}",
        status="info",
        finish=False,
        progress=98,
    )
    updateTask(
        task.id,
        f"Profile gasite pe olt ca fiind folosite de catre un ont : {len(used_found_profiles)}",
        status="info",
        finish=False,
        progress=99,
    )
    updateTask(
        task.id,
        f"Profile ce nu au putut fi sterse din baza de date : {failed_to_delete_profiles}",
        status="info",
        finish=True,
        progress=100,
    )


def delete_onu_traffic_profile_task(ont_traffic_profile, username):

    profile_name = ont_traffic_profile.name
    job = get_current_job()
    olt = OLT.query.filter_by(id=ont_traffic_profile.olt_id).first()
    task = Task(
        id=job.get_id(),
        olt_id=olt.id,
        name="delete_onu_traffic_profile_task",
        description=f"Deleting an onu traffic profile",
        status="waiting",
        username=username,
    )
    db.session.add(task)
    db.session.commit()
    try:
        libLogger.debug(
            f"Got a request to delete onu traffic profile with id: {ont_traffic_profile.id}"
        )
        if ont_traffic_profile:

            updateTask(
                task.id,
                "Se incepe stergerea profilului de trafic al ont-ului",
                status="info",
                finish=False,
                progress=5,
            )

            updateTask(
                task.id,
                "Se conecteaza la olt prin telnet pentru stergerea profilului..",
                status="info",
                finish=False,
                progress=30,
            )
            ds = DasanReader(olt)
            delete_onu_profile_command = (
                f"conf t" + "\ngpon" + f"\nno traffic-profile {profile_name}" + "\nend"
            )
            updateTask(
                task.id,
                "Se sterge profilul de traffic prin telnet..",
                status="info",
                finish=False,
                progress=50,
            )
            # Vom verifica comanda linie cu linie, pentru a verifica daca exista error in raspuns..
            not_found_on_olt = False
            for line_of_command in delete_onu_profile_command.splitlines():
                libLogger.debug(f"Sending command: {line_of_command}")
                command_result = ds.sendtelnetCommand(line_of_command)
                if "No exist Entry" in command_result:
                    libLogger.warning(
                        f"Numele de profil {profile_name} nu a fost gasit pe olt !"
                    )
                    updateTask(
                        task.id,
                        f"Numele de profil {profile_name} nu a fost gasit pe olt !",
                        status="error",
                        finish=False,
                        progress=60,
                    )
                    not_found_on_olt = True
                elif "is used by onu-profile" in command_result:
                    libLogger.warning(
                        f"Profilul {profile_name} are profile de ont asociate pe olt!"
                    )
                    updateTask(
                        task.id,
                        f"Profilul {profile_name} are profile de ont asociate pe olt",
                        status="error",
                        finish=False,
                        progress=100,
                    )
                    return return_error(
                        f"Profilul {profile_name} are profile de ont asociate pe olt",
                        409,
                    )
            if not not_found_on_olt:
                libLogger.warning(f"Profilul {profile_name} a fost sters de pe olt!")
                updateTask(
                    task.id,
                    f"Profilul {profile_name} a fost sters de pe olt!",
                    status="info",
                    finish=False,
                    progress=80,
                )

            # db.session.delete(ont_traffic_profile)
            DasanTrafficProfiles.query.filter_by(id=ont_traffic_profile.id).delete()
            commit_result = safe_commit(
                success_msg=f"Successfully deleted onu traffic profile {ont_traffic_profile.id}",
                success_code=200,
                error_msg=f"Failled to delete onu traffic profile {ont_traffic_profile.id} from DB",
                error_code=417,
            )

            if commit_result[1] == 200:
                libLogger.debug(commit_result[0])
                updateTask(
                    task.id,
                    "Profilul de traffic al ont-ului a fost sters din baza de date, success!",
                    status="info",
                    finish=True,
                    progress=100,
                )

                return return_success("Stergerea a luat sfarsit cu success!", 200)
            else:
                libLogger.error(commit_result[0])
                updateTask(
                    task.id,
                    "Profilul de traffic NU a putut fi sters din baza de date!, se amana stergerea..",
                    status="error",
                    finish=True,
                    progress=100,
                )
                return return_error(
                    f"Profilul de traffic NU a putut fi sters din baza de date!", 404
                )
        else:
            libLogger.warning(
                f"Nu a fost gasit profilul cu id:{ont_traffic_profile.id}"
            )
            updateTask(
                task.id,
                f"Nu a fost gasit profilul cu id:{ont_traffic_profile.id} in baza de date.., se amana stergerea",
                status="error",
                finish=True,
                progress=100,
            )
            return return_error(
                f"Nu a fost gasit profilul cu id:{ont_traffic_profile.id}", 404
            )
    except Exception as e:
        db.session.rollback()
        libLogger.error(f"Error: {str(e)}")
        libLogger.exception(e)
        updateTask(
            task.id,
            f"Profilul de trafic nu a putut fi şters, eroare necunoscuta..",
            status="error",
            finish=True,
            progress=100,
        )
        return return_error(f"Profilul nu a putut fi şters", 404)


def delete_onu_profile_task(ont_profile, username):
    job = get_current_job()
    task = Task(
        id=job.get_id(),
        olt_id=ont_profile.olt_id,
        name="delete_onu_profile_task",
        description=f"Deleting an onu profile",
        status="waiting",
        username=username,
    )
    db.session.add(task)
    db.session.commit()
    olt = OLT.query.filter_by(id=ont_profile.olt_id).first()
    libLogger.debug(f"Got a request to delete onu profile with id: {ont_profile.id}")
    try:
        updateTask(
            task.id,
            "Se incepe stergerea profilului de ont",
            status="info",
            finish=False,
            progress=5,
        )

        updateTask(
            task.id,
            "Se conecteaza la olt prin telnet pentru stergerea profilului..",
            status="info",
            finish=False,
            progress=10,
        )
        ds = DasanReader(olt)
        delete_onu_profile_command = (
            f"conf t" + "\ngpon" + f"\nno onu-profile {ont_profile.name}" + "\nend"
        )
        updateTask(
            task.id,
            "Se sterge profilul de ont prin telnet..",
            status="info",
            finish=False,
            progress=50,
        )
        # Vom verifica comanda linie cu linie, pentru a verifica daca exista error in raspuns..
        for line_of_command in delete_onu_profile_command.splitlines():
            libLogger.debug(f"Sending command: {line_of_command}")
            command_result = ds.sendtelnetCommand(line_of_command)
            if "No exist Entry" in command_result:
                libLogger.warning(
                    f"Numele de profil {ont_profile.name} nu a fost gasit pe olt !"
                )
                updateTask(
                    task.id,
                    f"Numele de profil {ont_profile.name} nu a fost gasit pe olt !",
                    status="error",
                    finish=False,
                    progress=80,
                )
            elif "Applied profile to onu, can't delete" in command_result:
                libLogger.warning(
                    f"Profilul {ont_profile.name} are ont-uri asociate pe olt!"
                )
                updateTask(
                    task.id,
                    f"Profilul {ont_profile.name} are ont-uri asociate pe olt!",
                    status="error",
                    finish=False,
                    progress=100,
                )
                return return_error(
                    f"Profilul {ont_profile.name} are ont-uri asociate pe olt!", 409
                )

        db.session.delete(ont_profile)

        commit_result = safe_commit(
            success_msg=f"Successfully deleted onu profile {ont_profile.id}",
            success_code=200,
            error_msg=f"Failled to delete onu profile {ont_profile.id} from DB",
            error_code=417,
        )

        if commit_result[1] == 200:
            libLogger.debug(commit_result[0])
            updateTask(
                task.id,
                "Profilul de ont a fost sters din baza de date,success!",
                status="info",
                finish=True,
                progress=100,
            )
            libLogger.debug(f"Stergerea a luat sfarsit cu success!")
            return return_success("Stergerea a luat sfarsit cu success!", 200)
        else:
            libLogger.error(commit_result[0])
            updateTask(
                task.id,
                "Profilul de ont NU a putut fi sters din baza de date!, se amana stergerea..",
                status="error",
                finish=True,
                progress=100,
            )
            return return_error(
                f"Profilul de ont NU a putut fi sters din baza de date!", 404
            )
    except Exception as e:
        db.session.rollback()
        libLogger.error(f"Error: {str(e)}")
        libLogger.exception(e)
        updateTask(
            task.id,
            f"Profilul nu a putut fi şters, eroare necunoscuta..",
            status="error",
            finish=True,
            progress=100,
        )
        return return_error(f"Profilul nu a putut fi şters", 404)


def delete_ont_task(data):
    ont_query = ONT.query.filter_by(id=data["ont_id"])
    ont = ont_query.first()

    try:
        if ont:
            interface_object = Interfaces.query.filter_by(id=ont.interface_id).first()
            interface = interface_object.ifDescr.split("-")[1]

            ont_id = ont.ont_id
            job = get_current_job()
            olt = OLT.query.filter_by(id=ont.olt_id).first()
            task = Task(
                id=job.get_id(),
                olt_id=olt.id,
                name="delete_onu_task",
                description=f"Deleting an onu",
                status="waiting",
                username=data["username"],
            )
            db.session.add(task)
            db.session.commit()

            updateTask(
                task.id,
                "Se conecteaza la olt prin telnet pentru stergerea ont-ului..",
                status="info",
                finish=False,
                progress=10,
            )
            libLogger.debug(f"Connecting trough telnet to the olt.. ")
            ds = DasanReader(olt)
            delete_onu_command = (
                f"conf t"
                + "\ngpon"
                + f"\ngpon-olt {interface}"
                + f"\nno onu {ont_id}"
                + "\nend"
            )
            updateTask(
                task.id,
                "Se sterge ont-ul prin telnet..",
                status="info",
                finish=False,
                progress=50,
            )
            # Vom verifica comanda linie cu linie, pentru a verifica daca exista error in raspuns..
            for line_of_command in delete_onu_command.splitlines():
                libLogger.debug(f"Sending command: {line_of_command}")
                command_result = ds.sendtelnetCommand(line_of_command)
                libLogger.debug(f"Command result: {command_result}")

                if "Invalid range:" in command_result:
                    libLogger.warning(f"Id-ul ONT-ului: {ont_id}, este invalid!")
                    updateTask(
                        task.id,
                        f"Id-ul ONT-ului: {ont_id}, este invalid!",
                        status="error",
                        finish=False,
                        progress=60,
                    )
                elif "Fail to delete onu" in command_result:
                    libLogger.warning(
                        f"ONT-ul cu id {ont_id}, nu a putut fi sters prin telnet, poate acesta nu exista pe olt?"
                    )
                    updateTask(
                        task.id,
                        f"ONT-ul cu id {ont_id}, nu a putut fi sters prin telnet, poate acesta nu exista pe olt?",
                        status="error",
                        finish=False,
                        progress=60,
                    )
                elif "Applied profile to onu, can't delete" in command_result:
                    libLogger.warning(f"ONT-ul cu id-ul {ont_id} are profile asociate!")
                    updateTask(
                        task.id,
                        f"ONT-ul cu id-ul {ont_id} are profile asociate!",
                        status="error",
                        finish=False,
                        progress=100,
                    )
                    return return_error(
                        f"ONT-ul cu id-ul {ont_id} are profile asociate!", 409
                    )

            ont_query.delete()

            commit_result = safe_commit(
                success_msg=f"Successfully deleted onu {data['ont_id']}",
                success_code=200,
                error_msg=f"Failled to delete onu {data['ont_id']} from DB",
                error_code=417,
            )

            if commit_result[1] == 200:
                libLogger.debug(commit_result[0])
                updateTask(
                    task.id,
                    "Ont-ul a fost sters din baza de date,success!",
                    status="info",
                    finish=True,
                    progress=100,
                )

                libLogger.debug(f"Stergerea a luat sfarsit cu success!")
                return return_success("Stergerea a luat sfarsit cu success!", 200)
            else:
                libLogger.error(commit_result[0])
                updateTask(
                    task.id,
                    "Ont-ul NU a putut fi sters din baza de date!, se amana stergerea..",
                    status="error",
                    finish=True,
                    progress=100,
                )
                return return_error(
                    f"Ont-ul NU a putut fi sters din baza de date!", 404
                )
        else:
            libLogger.warning(f"Nu a fost gasit ONT-ul cu id:{data['ont_id']}")
            updateTask(
                task.id,
                f"Nu a fost gasit ONT-ul cu id:{data['ont_id']} in baza de date.., se amana stergerea",
                status="error",
                finish=True,
                progress=100,
            )
            return return_error(f"Nu a fost gasit ONT-ul cu id:{data['ont_id']}", 404)
    except Exception as e:
        db.session.rollback()
        libLogger.error(f"Error: {str(e)}")
        libLogger.exception(e)
        updateTask(
            task.id,
            f"ONT-ul nu a putut fi şters, eroare necunoscuta..",
            status="error",
            finish=True,
            progress=100,
        )
        return return_error(f"ONT-ul nu a putut fi şters", 404)


def configNewOnt_task(data):
    job = get_current_job()
    olt = OLT.query.filter_by(id=data["olt_id"]).first()
    task = Task(
        id=job.get_id(),
        olt_id=olt.id,
        name="configure_ont",
        description=f"configure new ont",
        status="waiting",
        username=data["username"],
    )
    db.session.add(task)
    db.session.commit()
    data["task"] = task
    configure_ont(data)


def ReadONTConfig_task(ont, data):
    job = get_current_job()
    olt = OLT.query.filter_by(id=ont.olt_id).first()
    task = Task(
        id=job.get_id(),
        olt_id=olt.id,
        name="ReadONTConfig_task",
        description=f"read ont configuration",
        status="waiting",
        username=data["username"],
    )
    db.session.add(task)
    db.session.commit()
    updateTask(
        task.id, "Se preiau informatii despre interfetele " + olt.hostname, progress=5
    )
    interface = get_interface(ont.interface_id)
    updateTask(task.id, "Se preia configul ont-ului", progress=10)
    reader_object = DasanReader(olt)
    ont_cfg = reader_object.ReadONTConfig(ont, interface)
    if ont_cfg is False:
        updateTask(
            task.id, "Eroare la citirea tatelor prin SNMP", status="error", finish=True
        )
        return
    if ont_cfg["description"] != ont.description:
        ont_updated = True
        ont.description = ont_cfg["description"]
    # Cheking for model in here
    actual_device_model = DeviceModel.query.filter_by(model=ont_cfg["model"]).first()
    if actual_device_model:
        if actual_device_model.id != ont.device_model_id:
            ont.device_model_id = actual_device_model.id
    else:
        libLogger.warning(
            f"Device model {ont_cfg['model']} doesnt exist in olt database!"
        )

    # Checking for mac in here
    for ch in [":", ".", "-", " "]:
        if ch in ont_cfg["mac"]:
            ont_cfg["mac"] = ont_cfg["mac"].replace(ch, "")
    mac_int = int(ont_cfg["mac"], 16)
    if ont.mac_int != mac_int:
        ont.mac_int = mac_int
    # Cheking for profiles in here
    updateTask(task.id, "Se preiau informatii despre ONT profile", progress=40)
    actual_onu_profile = DasanONTProfiles.query.filter_by(
        name=ont_cfg["onu_profile"]
    ).first()
    if actual_onu_profile:
        if actual_onu_profile.id != ont.dasan_ont_profile_id:
            ont.dasan_ont_profile_id = actual_onu_profile.id
    else:
        libLogger.warning(
            f"Profile {ont_cfg['onu_profile']} doesnt exist in olt database!"
        )
    # Checking for optical rx power in here
    if ont_cfg["oltrxpower"]:
        ont.oltrxpower = ont_cfg["oltrxpower"]

    if ont_cfg["rxpower"]:
        ont.rxpower = ont_cfg["rxpower"]

    # Checking for wifi_status in here
    updateTask(task.id, "Se preiau informatii despre Wi-Fi status", progress=50)
    ont_wifi = ONTWifi.query.filter(ONTWifi.ont_id == ont.id).first()
    if ont_cfg["wifi_status"] != "NOSUCHINSTANCE":
        if ont_wifi:
            ont_wifi.oper_status = ont_cfg["wifi_status"]
        else:
            ont_wifi = ONTWifi(
                ont_id=ont.id,
                oper_status=ont_cfg["wifi_status"],
                admin_status=ont_cfg["wifi_status"],
                instance=1,
            )
            db.session.add(ont_wifi)

    # Checking for username/pass in here
    if "username" in ont_cfg:
        ont.username = ont_cfg["username"]
    else:
        libLogger.warning("Couln't get the username from the ont")
    if "password" in ont_cfg:
        ont.password = ont_cfg["password"]
    else:
        libLogger.warning("Couln't get the password from the ont")

    updateTask(task.id, "Se preiau informatii despre starea video", progress=60)
    ont_catv = ONTCATV.query.filter(ONTCATV.ont_id == ont.id).first()
    if "video" in ont_cfg:
        if ont_catv:
            ont_catv.admin_status = ont_cfg["video"]["admin_status"]
            ont_catv.oper_status = ont_cfg["video"]["oper_status"]
            ont_catv.optical_rx = ont_cfg["video"]["optical_rx"]
            ont_catv.rf_tx = ont_cfg["video"]["rf_tx"]
        else:
            ont_catv = ONTCATV(
                ont_id=ont.id,
                admin_status=ont_cfg["video"]["admin_status"],
                oper_status=ont_cfg["video"]["oper_status"],
                optical_rx=ont_cfg["video"]["optical_rx"],
                rf_tx=ont_cfg["video"]["rf_tx"],
            )
            db.session.add(ont_catv)
    else:
        libLogger.warning("Couln't get the video from then ont")

    ont.upTime = ont_cfg["uptime"]
    if int(ont_cfg["status"]) != ont.status:
        ont.status = ont_cfg["status"]
    if ont_cfg["sn"] != ont.sn:
        ont.sn = ont_cfg["sn"]
    if ont_cfg["firmware"] != ont.firmware:
        ont.firmware = ont_cfg["firmware"]

    # Checking for voip in here
    updateTask(task.id, "Se preiau informatii despre VOIP-uri", progress=75)
    active_voip_services = len(ont_cfg["voip"]["nr"])
    ont_voip = ONTVoip.query.filter_by(ont_id=ont.id).first()
    if active_voip_services == 1:
        if ont_voip:
            ont_voip.phone_number = ont_cfg["voip"]["nr"][0]
            ont_voip.password = ont_cfg["voip"]["auth"][0]
            ont_voip.status = ont_cfg["voip"]["status"][0]
            ont_voip.pots = 1
        else:
            phone_number = ont_cfg["voip"]["nr"][0]
            password = ont_cfg["voip"]["auth"][0]
            status = ont_cfg["voip"]["status"][0]

            ont_voip_row = ONTVoip(
                ont_id=ont.id,
                pots=1,
                phone_number=phone_number,
                password=password,
                status=status,
            )
            db.session.add(ont_voip_row)
    elif active_voip_services == 0:
        libLogger.debug(f"There are no voip services for this ont")
    else:
        libLogger.warning(f"There are more than 1 voip services on ont {ont.id}")

    ont.last_update = datetime.datetime.now()
    updateTask(task.id, "Se scriu informatiile in baza de date", progress=90)
    db.session.add(ont)
    db.session.commit()
    updateTask(
        task.id, "Toate datele au fost colectate fara erori", progress=100, finish=True
    )
    libLogger.info("Task completed")
