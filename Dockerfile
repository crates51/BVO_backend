FROM python:3.9
ARG GIT_DESCRIBE

LABEL maintainer="nl2@next-gen.ro"
LABEL application="OLT"

RUN echo 'Acquire::http::proxy "http://188.173.1.120:3142";' > /etc/apt/apt.conf.d/02proxy
RUN apt-get update && apt-get install -y libsnmp-dev  # required for easysnmp 

WORKDIR /opt/OLT/
ADD requirements.txt /opt/OLT/
RUN pip install -r requirements.txt
ADD . /opt/OLT/
EXPOSE 6001

ENTRYPOINT ["./bootup.sh"]
CMD []
