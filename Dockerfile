FROM python:3.14-slim@sha256:0c6bb259d537411417dd3b0052730e237ec0b8bd66aeaf64f1804a142d5c23ae

WORKDIR /app
COPY dist/*.whl ./
RUN pip install *.whl && rm *.whl && pip cache purge

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
