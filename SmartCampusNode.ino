/*
  Smart Campus Energy and Environment Monitor
  Board: ESP32 DevKit

  Libraries to install in Arduino IDE:
  - WiFi, built into ESP32 Arduino core
  - HTTPClient
  - ArduinoJson
  - DHT sensor library by Adafruit

  Replace Wi-Fi values and dashboard URL before uploading.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "DHT.h"

#define DHTPIN 4
#define DHTTYPE DHT22
#define MQ135_PIN 34
#define PIR_PIN 27
#define CURRENT_PIN 35

const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* DASHBOARD_URL = "http://192.168.1.3:5000/api/telemetry";

const char* DEVICE_ID = "lab1-node1";

DHT dht(DHTPIN, DHTTYPE);
unsigned long lastPublishMs = 0;
const unsigned long publishIntervalMs = 5000;

float estimateCurrentAmps(int rawAdc) {
  float voltage = (rawAdc / 4095.0) * 3.3;
  float zeroCurrentVoltage = 1.65;
  float sensitivity = 0.185;
  float current = abs((voltage - zeroCurrentVoltage) / sensitivity);
  if (current < 0.05) return 0.0;
  return current;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Wi-Fi connected. IP: ");
  Serial.println(WiFi.localIP());
}

void postTelemetry() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi disconnected, reconnecting...");
    connectWiFi();
  }

  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
  int airQualityRaw = analogRead(MQ135_PIN);
  bool motion = digitalRead(PIR_PIN) == HIGH;
  int currentRaw = analogRead(CURRENT_PIN);
  float currentA = estimateCurrentAmps(currentRaw);
  float powerW = currentA * 230.0;

  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("DHT read failed");
    return;
  }

  StaticJsonDocument<256> doc;
  doc["device_id"] = DEVICE_ID;
  doc["temperature_c"] = temperature;
  doc["humidity_pct"] = humidity;
  doc["air_quality_raw"] = airQualityRaw;
  doc["motion"] = motion;
  doc["current_a"] = currentA;
  doc["power_w"] = powerW;

  char payload[256];
  size_t len = serializeJson(doc, payload);

  HTTPClient http;
  http.begin(DASHBOARD_URL);
  http.addHeader("Content-Type", "application/json");

  int httpResponse = http.POST((uint8_t*)payload, len);
  if (httpResponse > 0) {
    Serial.printf("Telemetry posted, status=%d\n", httpResponse);
  } else {
    Serial.printf("Telemetry post failed: %d\n", httpResponse);
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  dht.begin();
  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  unsigned long now = millis();
  if (now - lastPublishMs >= publishIntervalMs) {
    lastPublishMs = now;
    postTelemetry();
  }
}

