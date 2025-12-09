FROM python:3.14-slim@sha256:a86d0ed368c9f7572ef6a7d0b847e8d5a927ea4123bb5ea335f206702a0fa40d

WORKDIR /app
COPY dist/*.whl ./
RUN pip install *.whl && rm *.whl && pip cache purge

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
