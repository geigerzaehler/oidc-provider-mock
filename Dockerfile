FROM python:3.15-slim@sha256:80cd82871b55326f05d4c3a3b714b371b0e9833891de4be4eb4b99d3092e0029

WORKDIR /app
COPY requirements.txt dist/*.whl ./
RUN pip install -r requirements.txt && \
    pip install --no-deps *.whl && \
    rm requirements.txt *.whl && \
    pip cache purge

RUN pip check

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
