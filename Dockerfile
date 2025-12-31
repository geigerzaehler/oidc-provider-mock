FROM python:3.14-slim@sha256:f7864aa85847985ba72d2dcbcbafd7475354c848e1abbdf84f523a100800ae0b

WORKDIR /app
COPY dist/*.whl ./
RUN pip install *.whl && rm *.whl && pip cache purge

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
