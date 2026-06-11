FROM python:3.14-slim@sha256:81ada6cb56bcbe3909644b4cb76ebe5354c65eaaad788a437bc1340a7638d49d

WORKDIR /app
COPY requirements.txt dist/*.whl ./
RUN pip install -r requirements.txt && \
    pip install --no-deps *.whl && \
    rm requirements.txt *.whl && \
    pip cache purge

RUN pip check

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
