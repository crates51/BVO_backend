import os
import logging
import sys
from flask_migrate import Migrate, MigrateCommand
from flask_script import Manager
from app import create_app, db
from app.api import blueprint

# import redis
from rq import Connection, Worker
from app.models import user, product

try:
    import uwsgi
    import uwsgidecorators
except ImportError:
    UWSGI_ENABLED = False
    uwsgi = uwsgidecorators = None
else:
    UWSGI_ENABLED = True


env = os.environ


class ClientSideFilter(logging.Filter):
    def filter(self, rec):
        return "POST /Tasks/uncompleted" not in rec.getMessage()


class ColorFormatter(logging.Formatter):
    def format(self, record):
        if record.levelname == "INFO":
            record.msg = "\033[1;36m" + str(record.msg) + "\033[0m"
        elif record.levelname == "WARNING":
            record.msg = "\033[1;33m" + str(record.msg) + "\033[0m"
        elif record.levelname == "ERROR":
            record.msg = "\033[1;31m" + str(record.msg) + "\033[0m"
        elif record.levelname == "DEBUG":
            record.msg = "\033[0;95m" + str(record.msg) + "\033[0m"
        elif record.levelname == "CRITICAL":
            record.msg = "\033[1;41m" + str(record.msg) + "\033[0m"
        elif 5 <= record.levelno < 10:
            record.msg = "\033[0;32m" + str(record.msg) + "\033[0m"
        elif record.levelno <= 4:
            record.msg = "\033[0;94m" + str(record.msg) + "\033[0m"

        return super().format(record)


currentDirectory = os.path.dirname(os.path.realpath(__file__))
globalLogger = logging.getLogger("main")
globalLogger.setLevel(logging.INFO)

logging.getLogger("werkzeug").addFilter(ClientSideFilter())
consoleLogging = logging.StreamHandler(sys.stdout)
consoleLogging.setFormatter(
    ColorFormatter(
        "\033[1;37m%(asctime)s\033[0m : %(name)s/\033[0;30m\033[43m%(processName)s\033[0m/\033[44m%(threadName)s\033[0m %(levelname)s in %(funcName)s -> %(message)s"
    )
)
consoleLogging.setLevel(logging.INFO)

colorFileLogging = logging.FileHandler(currentDirectory + "/logs/call")
colorFileLogging.setFormatter(
    ColorFormatter(
        "\033[1;37m%(asctime)s\033[0m : %(name)s/\033[0;30m\033[43m%(processName)s\033[0m/\033[44m%(threadName)s\033[0m %(levelname)s in %(funcName)s -> %(message)s"
    )
)
colorFileLogging.setLevel(logging.INFO)

if "DEBUG_SQL" in env.keys():
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
else:
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARN)

if "VERBOSE" in env.keys():
    globalLogger.setLevel(1)
    consoleLogging.setLevel(1)
    colorFileLogging.setLevel(1)
elif "DEBUG" in env.keys():
    globalLogger.setLevel(logging.DEBUG)
    consoleLogging.setLevel(logging.DEBUG)
    colorFileLogging.setLevel(logging.DEBUG)
elif "QUIET" in env.keys():
    consoleLogging.setLevel(logging.WARN)
    consoleLogging.setLevel(logging.WARN)
    colorFileLogging.setLevel(logging.WARN)
else:
    globalLogger.setLevel(logging.INFO)

globalLogger.addHandler(colorFileLogging)
globalLogger.addHandler(consoleLogging)


app = create_app(os.getenv("ENV_TYPE") or "dev")
app.register_blueprint(blueprint)

app.app_context().push()

manager = Manager(app)
migrate = Migrate(app, db)
manager.add_command("db", MigrateCommand)


@manager.command
def run():
    globalLogger.info("starting flask app")
    app.run(host="0.0.0.0", port=6001)


@manager.command
def run_worker():
    with Connection(app.redis):
        # Rulam schedulerul din worker. Daca se pune in app/__init__.py va fi pornit si de catre app pricipala si de catre worker
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.schedulers import check_olt_status

        sched = BackgroundScheduler(daemon=True)
        sched.add_job(check_olt_status, "cron", hour="*", minute="*/5")
        sched.start()
        worker = Worker("olt-tasks")
        worker.work()


if __name__ == "__main__":
    manager.run()
