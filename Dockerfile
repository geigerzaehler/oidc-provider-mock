FROM python:3.14-slim@sha256:9006fc63e3eaedc00ebc81193c99528575a2f9b9e3fb36d95e94814c23f31f47

WORKDIR /app
COPY dist/*.whl ./
RUN pip install *.whl && rm *.whl && pip cache purge

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
