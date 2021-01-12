FROM python:3.9-alpine

RUN \
    apk add --no-cache \
        git=2.26.2-r0 \
    \
    && pip3 install \
        repository-updater==0.6.0

COPY lint.py /lint.py

ENTRYPOINT ["python3", "/lint.py"]
