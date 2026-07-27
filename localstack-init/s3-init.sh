#!/bin/bash
echo "🔧 Inicializando LocalStack S3..."

# Crear bucket
awslocal s3 mb s3://test-bucket

# Crear archivo de prueba
echo "Contenido de prueba para S3" > /tmp/sample.txt
awslocal s3 cp /tmp/sample.txt s3://test-bucket/test/sample.txt

echo "✅ Bucket test-bucket creado correctamente"