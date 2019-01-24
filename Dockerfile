FROM alpine:3.8

RUN apk --update upgrade
RUN apk add --no-cache --update \
    python3 \
  && pip3 install --upgrade pip \
  && pip3 install virtualenv \
  && virtualenv /env

WORKDIR /app
COPY requirements.txt /app/

RUN /env/bin/pip3 install -r requirements.txt

COPY vespa-exporter.py /app/

CMD ["/env/bin/python3", "/app/vespa-exporter.py"]
