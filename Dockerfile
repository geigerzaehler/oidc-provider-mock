FROM python:3.14-slim@sha256:3fa9f1158b0d8b5029c357770bd522e7955546ffc5db885d8b366ec4a687afd4

WORKDIR /app
COPY requirements.txt dist/*.whl ./
RUN pip install -r requirements.txt && \
    pip install --no-deps *.whl && \
    rm requirements.txt *.whl && \
    pip cache purge

RUN pip check

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
