FROM python:3.14-slim@sha256:0741d101873c12ab927e6f8653feb8862b9bd58771177acb1b885b95141f91b4

WORKDIR /app
COPY requirements.txt dist/*.whl ./
RUN pip install -r requirements.txt && \
    pip install --no-deps *.whl && \
    rm requirements.txt *.whl && \
    pip cache purge

RUN pip check

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
