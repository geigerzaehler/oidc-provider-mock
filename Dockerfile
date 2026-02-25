FROM python:3.14-slim@sha256:4f5f9ce230b88b941e26e26ac21317a98a4b0e02d1414b9b0e888fe4d7a51bc4

WORKDIR /app
COPY dist/*.whl ./
RUN pip install *.whl && rm *.whl && pip cache purge

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
