FROM alpine:3.5

RUN apk --update upgrade
RUN apk add --no-cache --update \
    python \
    py-pip \
  && pip install --upgrade pip \
  && pip install virtualenv \
  && virtualenv /env

WORKDIR /app
COPY requirements.txt /app/

RUN /env/bin/pip install -r requirements.txt

COPY vespa-exporter.py /app/

CMD ["/env/bin/python", "/app/vespa-exporter.py"]
