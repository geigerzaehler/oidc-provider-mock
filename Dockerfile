FROM python:3.14-slim@sha256:072ffcb57bab690052d9b695592d811a42b849e8ef254ced334a28f283d5f76a

WORKDIR /app
COPY requirements.txt dist/*.whl ./
RUN pip install -r requirements.txt && \
    pip install --no-deps *.whl && \
    rm requirements.txt *.whl && \
    pip cache purge

RUN pip check

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
