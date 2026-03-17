FROM python:3.14-slim@sha256:35f442c69294267a391b05d9526b6a330986ad9b008152a2e24257a1f98a8dc0

WORKDIR /app
COPY dist/*.whl ./
RUN pip install *.whl && rm *.whl && pip cache purge

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
