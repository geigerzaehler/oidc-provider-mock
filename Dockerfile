FROM python:3.14-slim@sha256:44513520b81338d2d12499a59874220b05988819067a2cbac4545750a68e4b2b

WORKDIR /app
COPY dist/*.whl ./
RUN pip install *.whl && rm *.whl && pip cache purge

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
