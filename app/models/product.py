from .. import db
import datetime

# from flask import current_app
# from app.models.ont import ONT


class Product(db.Model):
    """Products table"""

    __tablename__ = "products"

    id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer(), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Integer(), nullable=False)
    last_update = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.datetime.utcnow(),
    )

    # return ONT.query.filter_by(olt_id=self.id).count()


# class OLT(db.Model):
#     """OLTS"""

#     __tablename__ = "olts"

#     id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
#     hostname = db.Column(db.String(64), unique=True, nullable=False)
#     ip = db.Column(db.String(128), nullable=False)
#     device_model_id = db.Column(
#         db.Integer,
#         db.ForeignKey("device_models.id", ondelete="RESTRICT"),
#         nullable=False,
#     )
#     branch = db.Column(db.String(100), nullable=False)
#     snmpv2_community = db.Column(db.String(100), nullable=True)
#     snmpv2_write = db.Column(db.String(100), nullable=True)
#     fw_version = db.Column(db.String(64), nullable=True)
#     username = db.Column(db.String(32), nullable=True)
#     password = db.Column(db.String(32), nullable=True)
#     status = db.Column(db.String(10), nullable=False, default="new")
#     last_update = db.Column(
#         db.DateTime,
#         nullable=False,
#         default=datetime.datetime.utcnow(),
#         onupdate=datetime.datetime.utcnow(),
#     )
#     onts = db.relationship("ONT", backref="olt", lazy=True)


# @property
# def onts_count(self):
#     return ONT.query.filter_by(olt_id=self.id).count()

#     def launch_task(self, name, description, *args, **kwargs):
#         rq_job = current_app.task_queue.enqueue(
#             "app.tasks." + name, self.id, *args, **kwargs
#         )
#         task = Task(
#             id=rq_job.get_id(), name=name, description=description, olt_id=self.id
#         )
#         db.session.add(task)
#         db.session.commit()
#         return task

#     def get_tasks_in_progress(self):
#         return Task.query.filter_by(user=self, complete=False).all()

#     def get_task_in_progress(self, name):
#         return Task.query.filter_by(name=name, user=self, complete=False).first()


# class DBAProfiles(db.Model):
#     """DBA_Profiles"""

#     __tablename__ = "dba_profiles"

#     id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
#     olt_id = db.Column(
#         db.Integer(), db.ForeignKey("olts.id", ondelete="CASCADE"), nullable=False
#     )
#     name = db.Column(db.String(32), nullable=False)
#     mode = db.Column(db.String(32), nullable=False)
#     fixed = db.Column(db.Integer(), nullable=True)
#     maximum = db.Column(db.BigInteger(), nullable=True)
#     assured = db.Column(db.BigInteger(), nullable=True)


# class TargetFwVersions(db.Model):
#     """What fw version should have each olt/ont model"""

#     __tablename__ = "target_fw_versions"

#     id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
#     olt_id = db.Column(
#         db.Integer(), db.ForeignKey("olts.id", ondelete="CASCADE"), nullable=False
#     )
#     device_model_id = db.Column(
#         db.Integer(), db.ForeignKey("device_models.id"), nullable=False
#     )
#     filename = db.Column(db.String(32), nullable=False)


# class OLTSlots(db.Model):
#     """Slots on OLT"""

#     __tablename__ = "olt_slots"

#     id = db.Column("id", db.Integer(), autoincrement=True, nullable=False)
#     olt_id = db.Column(
#         db.Integer(), db.ForeignKey("olts.id", ondelete="CASCADE"), nullable=False
#     )
#     db.PrimaryKeyConstraint(id, id)
#     name = db.Column("name", db.String(length=32), nullable=False)
#     serial = db.Column("serial", db.String(length=32), nullable=True)
#     model = db.Column("model", db.String(length=32), nullable=True)
#     hw_revision = db.Column("hw_revision", db.String(length=32), nullable=True)
#     pk_version = db.Column("pk_version", db.String(length=32), nullable=True)
#     nos_version = db.Column("nos_version", db.String(length=32), nullable=True)
#     uptime = db.Column("uptime", db.String(length=32), nullable=True)
#     cpu = db.Column("cpu", db.String(length=32), nullable=True)
#     free_memory = db.Column("free_memory", db.String(length=32), nullable=True)
#     total_memory = db.Column("total_memory", db.String(length=32), nullable=True)


# class OLTVlans(db.Model):
#     """Vlans configured on OLT"""

#     __tablename__ = "olt_vlans"

#     id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
#     olt_id = db.Column(
#         db.Integer(), db.ForeignKey("olts.id", ondelete="CASCADE"), nullable=False
#     )
#     name = db.Column(db.String(32), nullable=True)
#     vid = db.Column(db.SmallInteger(), nullable=False)
#     cos = db.Column(db.SmallInteger(), nullable=True)


# class VoipProfiles(db.Model):
#     """Voip Profile"""

#     __tablename__ = "voip_profiles"

#     id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
#     olt_id = db.Column(
#         db.Integer(), db.ForeignKey("olts.id", ondelete="CASCADE"), nullable=False
#     )
#     name = db.Column(db.String(32), nullable=True)
#     proxy_server = db.Column(db.String(32), nullable=True)
#     server = db.Column(db.String(32), nullable=False)
#     traffic_profile = db.relationship(
#         "DasanTrafficProfiles", backref="voip_profile", lazy=True
#     )


# class DasanTPVlans(db.Model):
#     """ONT traffic profile vlans (for each ont port)"""

#     __tablename__ = "dasan_tp_vlans"

#     id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
#     dasan_tp_services_id = db.Column(
#         db.Integer(),
#         db.ForeignKey("dasan_tp_services.id", ondelete="CASCADE"),
#         nullable=False,
#     )
#     vid = db.Column(db.Integer(), nullable=False)
#     tag = db.Column(db.Boolean(), nullable=False, default=False)


# class DasanTPPorts(db.Model):
#     """ONT traffic profile ports"""

#     __tablename__ = "dasan_tp_ports"

#     id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
#     dasan_tp_services_id = db.Column(
#         db.Integer(),
#         db.ForeignKey("dasan_tp_services.id", ondelete="CASCADE"),
#         nullable=False,
#     )
#     port = db.Column(db.String(16), nullable=True)
#     # Wheter the port is nat or bridge -> 1 = Nat, 0 = Bridge
#     nat = db.Column(db.Boolean(), nullable=False)
#     mgmt_mode = db.Column(db.String(32), nullable=True)


# class DasanTPServices(db.Model):
#     """dasan traffic profile service
#     pe dasan - include tcont - mapper - bridge din traffic profile
#     partea de porturi si vlanuri pt fiecare serviciu sunt in DasanTPPorts si DasanTPVlans
#     """

#     __tablename__ = "dasan_tp_services"

#     id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
#     dasan_traffic_profile_id = db.Column(
#         db.Integer(),
#         db.ForeignKey("dasan_traffic_profiles.id", ondelete="CASCADE"),
#         nullable=False,
#     )
#     service_id = db.Column(db.SmallInteger(), nullable=False)
#     ip_type = db.Column(db.Boolean(), nullable=True)  # 0 - static , 1 - dhcp
#     dba_id = db.Column(db.Integer(), db.ForeignKey("dba_profiles.id"), nullable=True)
#     rate_limit = db.Column(
#         db.Integer(),
#         db.ForeignKey("rate_limit_profiles.id", ondelete="CASCADE"),
#         nullable=True,
#     )
#     tp_ports = db.relationship("DasanTPPorts", backref="tp_service", lazy=True)
#     tp_vlans = db.relationship("DasanTPVlans", backref="tp_vlans", lazy=True)


# class DasanTrafficProfiles(db.Model):
#     """dasan traffic profile"""

#     __tablename__ = "dasan_traffic_profiles"

#     id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
#     olt_id = db.Column(
#         db.Integer(), db.ForeignKey("olts.id", ondelete="CASCADE"), nullable=False
#     )
#     name = db.Column(db.String(128), nullable=False)
#     voip_profile_id = db.Column(
#         db.Integer(),
#         db.ForeignKey("voip_profiles.id", ondelete="RESTRICT"),
#         nullable=True,
#     )
#     voip_vlan = db.Column(db.SmallInteger(), nullable=True)
#     tp_services = db.relationship(
#         "DasanTPServices", backref="dasan_traffic_profile", lazy=True
#     )
#     ont_profiles = db.relationship(
#         "DasanONTProfiles", backref="traffic_profile", lazy=True
#     )


# class DasanONTProfiles(db.Model):
#     """dasan ont profile"""

#     __tablename__ = "dasan_ont_profiles"

#     id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
#     olt_id = db.Column(
#         db.Integer(), db.ForeignKey("olts.id", ondelete="CASCADE"), nullable=False
#     )
#     dasan_traffic_profile_id = db.Column(
#         db.Integer(),
#         db.ForeignKey("dasan_traffic_profiles.id", ondelete="RESTRICT"),
#         nullable=False,
#     )
#     name = db.Column(db.String(128), nullable=False)
#     onts = db.relationship("ONT", backref="ont_profile", lazy=True)


# class RateLimitProfiles(db.Model):
#     """ont service ports ( pe dasan - trafic-profiles > bridge (fiecare bridge e un serviciu))"""

#     __tablename__ = "rate_limit_profiles"

#     id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
#     olt_id = db.Column(
#         db.Integer(), db.ForeignKey("olts.id", ondelete="CASCADE"), nullable=False
#     )
#     name = db.Column(db.String(32), nullable=True)
#     u_pir = db.Column(db.Integer(), nullable=False)
#     u_sir = db.Column(db.Integer(), nullable=False)
#     d_pir = db.Column(db.Integer(), nullable=False)
#     d_sir = db.Column(db.Integer(), nullable=False)


# class IPPool(db.Model):
#     """ ONT Model for storing ont details """

#     __tablename__ = "ip_pool"

#     id = db.Column(db.Integer, primary_key=True, autoincrement=True)
#     olt_id = db.Column(
#         db.Integer(), db.ForeignKey("olts.id", ondelete="CASCADE"), nullable=False
#     )
#     network = db.Column(db.String(136), nullable=False)  # x.x.x.x/x
#     gateway = db.Column(db.String(128), nullable=True)
#     vid = db.Column(db.Integer(), nullable=True)
#     ip_address = db.relationship("IPAddress", backref="ippool", lazy=True)
