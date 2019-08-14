## Exporting Vespa metrics to Prometheus

Specify vespa-configserver (hostname:port) in environment VESPA_CONFIGSERVER

Usage with docker

    # docker build -t vespa-exporter .
    # docker run -e VESPA_CONFIGSERVER=vespa-configserver.example.com:19071 vespa-exporter

If you are running your vespa container locally, remember to add `--network=host` to your `docker run` command.
