FROM python:3.14-slim@sha256:9b9a75b908891c42b7af174dcf3f6534ebcedfc28c874c6281eb452e86470e3e

WORKDIR /app
COPY dist/*.whl ./
RUN pip install *.whl && rm *.whl && pip cache purge

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
