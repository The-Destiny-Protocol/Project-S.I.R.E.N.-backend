#!/usr/bin/env bash
# scripts/generate_pki.sh
# Generates a local CA and mTLS certificates for backend & IoT edge nodes.

set -e

mkdir -p certs
cd certs

echo "🔒 Generating CA Private Key and Certificate..."
openssl req -x509 -newkey rsa:4096 -days 365 -nodes -keyout ca.key -out ca.crt -subj "/CN=SIH Ambulance CA"

echo "🔒 Generating Server Key and CSR (for Broker)..."
openssl req -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj "/CN=broker.local"
echo "🔒 Signing Server Certificate..."
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365

echo "🔒 Generating Backend Client Key and CSR..."
openssl req -newkey rsa:2048 -nodes -keyout backend.key -out backend.csr -subj "/CN=backend_service"
echo "🔒 Signing Backend Certificate..."
openssl x509 -req -in backend.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out backend.crt -days 365

echo "🔒 Generating IoT Edge Node (Ambulance) Key and CSR..."
openssl req -newkey rsa:2048 -nodes -keyout ambulance_edge.key -out ambulance_edge.csr -subj "/CN=ambulance_001"
echo "🔒 Signing IoT Edge Node Certificate..."
openssl x509 -req -in ambulance_edge.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out ambulance_edge.crt -days 365

echo "✅ PKI Generation Complete! Certificates located in ./certs"
echo "To use in backend, set .env variables:"
echo "MQTT_CA_CERT_PATH=certs/ca.crt"
echo "MQTT_CLIENT_CERT_PATH=certs/backend.crt"
echo "MQTT_CLIENT_KEY_PATH=certs/backend.key"
