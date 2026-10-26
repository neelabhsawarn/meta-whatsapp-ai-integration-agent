FROM python:3.12-slim
WORKDIR /code
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .
RUN mkdir -p /code/runtime
EXPOSE 8000
# Provide environment at runtime (never bake credentials into image).
CMD ["uvicorn", "app.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
