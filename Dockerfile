FROM python:3.14-slim@sha256:b0c4ec81396588a94b99052caf2f786e6e92e03111991d3d40c68762ee48d2ab

WORKDIR /app
COPY requirements.txt dist/*.whl ./
RUN pip install -r requirements.txt && \
    pip install --no-deps *.whl && \
    rm requirements.txt *.whl && \
    pip cache purge

RUN pip check

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
