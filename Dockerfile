FROM python:3.14-slim@sha256:5804723d159b38c72a2017e9d6d626c7cbe2f2f232fef593873cd63fee31c867

WORKDIR /app
COPY dist/*.whl ./
RUN pip install *.whl && rm *.whl && pip cache purge

EXPOSE 9400

ENTRYPOINT ["oidc-provider-mock", "--host", "0.0.0.0"]
