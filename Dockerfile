FROM python:3.14-slim@sha256:6a27522252aef8432841f224d9baaa6e9fce07b07584154fa0b9a96603af7456

WORKDIR /app
COPY dist/*.whl ./
RUN pip install *.whl && rm *.whl && pip cache purge

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
