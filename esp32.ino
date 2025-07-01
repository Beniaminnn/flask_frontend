#include <Arduino.h>

// Definire constante
#define NUM_SENSORS 4
#define MAX_DISTANCE 400
#define MIN_DISTANCE 10
#define TIMEOUT 30000
#define SAMPLE_INTERVAL 50
#define ROOM_WIDTH 400
#define ROOM_HEIGHT 400
#define MOTION_THRESHOLD 15.0
#define STABLE_COUNT 10
#define BASELINE_CALIBRATION_TIME 10000  // 1 minut pentru calibrare inițială
#define BASELINE_UPDATE_INTERVAL 50000  // 5 minute pentru actualizare
#define DT (SAMPLE_INTERVAL / 1000.0)
#define MAX_PEOPLE 3
#define DEBUG 1
#define CLUSTER_DISTANCE_THRESHOLD 50.0
#define VELOCITY_SMOOTHING 0.8
#define SERIAL_BAUD_RATE 115200
#define MIN_TRANSMISSION_INTERVAL 500  // Creștem intervalul minim la 500ms
#define POSITION_PRECISION 1
#define VELOCITY_PRECISION 2
#define DISTANCE_PRECISION 0
#define MIN_DETECTION_DISTANCE 30.0
#define DEVIATION_THRESHOLD 5.0  // Prag pentru stabilitatea baseline-ului

const int trigPins[NUM_SENSORS] = {13, 12, 14, 27}; // Dreapta, Stânga, Față, Spate
const int echoPins[NUM_SENSORS] = {15, 4, 5, 18};   // Dreapta, Stânga, Față, Spate

struct SensorData {
  float distance = -1.0;
  float lastDistance = -1.0;
  float baseline = MAX_DISTANCE;
  float maxDistance = MAX_DISTANCE;
  bool stable = true;
  float smoothedDistance = -1.0;
  float movingAverage[10] = {0};  // Buffer pentru medie mobilă
  uint8_t avgIndex = 0;
  float deviation = 0.0;
};

struct KalmanState {
  float x = ROOM_WIDTH / 2;
  float y = ROOM_HEIGHT / 2;
  float vx = 0.0;
  float vy = 0.0;
  float ax = 0.0;
  float ay = 0.0;
  float P[6][6] = {{25.0, 0, 0, 0, 0, 0},
                   {0, 25.0, 0, 0, 0, 0},
                   {0, 0, 5.0, 0, 0, 0},
                   {0, 0, 0, 5.0, 0, 0},
                   {0, 0, 0, 0, 1.0, 0},
                   {0, 0, 0, 0, 0, 1.0}};
  float Q[6][6] = {{0.5, 0, 0, 0, 0, 0},
                   {0, 0.5, 0, 0, 0, 0},
                   {0, 0, 0.2, 0, 0, 0},
                   {0, 0, 0, 0.2, 0, 0},
                   {0, 0, 0, 0, 0.1, 0},
                   {0, 0, 0, 0, 0, 0.1}};
  float R[2][2] = {{10.0, 0},
                   {0, 10.0}};
  unsigned long lastUpdateTime = 0;
};

struct PersonState {
  KalmanState kalman;
  bool active = false;
  float confidence = 0.0;
  unsigned long lastSeenTime = 0;
};

SensorData sensors[NUM_SENSORS];
PersonState people[MAX_PEOPLE];
unsigned long lastMeasureTime = 0;
unsigned long lastBaselineUpdate = 0;
unsigned long lastTransmissionTime = 0;
int stableCounter = 0;
char jsonBuffer[384];
bool dataChanged = false;
bool initialCalibration = true;

// Funcție îmbunătățită pentru măsurarea distanței cu filtrare
float measureDistance(int trigPin, int echoPin) {
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  unsigned long duration = pulseIn(echoPin, HIGH, TIMEOUT);
  if (duration == 0) return -1.0;

  float distance = duration * 0.0343 / 2;
  if (distance < MIN_DISTANCE || distance > MAX_DISTANCE) return -1.0;
  
  return distance;
}

// Funcție pentru netezirea măsurătorilor senzorilor
void smoothSensorData(int sensorIndex, float newDistance) {
  if (newDistance > 0) {
    if (sensors[sensorIndex].smoothedDistance < 0) {
      sensors[sensorIndex].smoothedDistance = newDistance;
    } else {
      float alpha = 0.3;
      sensors[sensorIndex].smoothedDistance = alpha * newDistance + (1 - alpha) * sensors[sensorIndex].smoothedDistance;
    }
  }
}

void kalmanPredict(KalmanState &kalman) {
  unsigned long currentTime = millis();
  float dt = DT;
  
  if (kalman.lastUpdateTime > 0) {
    dt = (currentTime - kalman.lastUpdateTime) / 1000.0;
    dt = constrain(dt, 0.01, 0.2);
  }
  kalman.lastUpdateTime = currentTime;

  float F[6][6] = {{1.0, 0, dt, 0, 0.5 * dt * dt, 0},
                   {0, 1.0, 0, dt, 0, 0.5 * dt * dt},
                   {0, 0, 1.0, 0, dt, 0},
                   {0, 0, 0, 1.0, 0, dt},
                   {0, 0, 0, 0, 0.9, 0},
                   {0, 0, 0, 0, 0, 0.9}};

  float x_pred[6] = {
    kalman.x + kalman.vx * dt + 0.5 * kalman.ax * dt * dt,
    kalman.y + kalman.vy * dt + 0.5 * kalman.ay * dt * dt,
    kalman.vx + kalman.ax * dt,
    kalman.vy + kalman.ay * dt,
    kalman.ax * 0.9,
    kalman.ay * 0.9
  };
  
  kalman.x = x_pred[0];
  kalman.y = x_pred[1];
  kalman.vx = x_pred[2];
  kalman.vy = x_pred[3];
  kalman.ax = x_pred[4];
  kalman.ay = x_pred[5];

  float P_temp[6][6] = {{0}};
  for (int i = 0; i < 6; i++) {
    for (int j = 0; j < 6; j++) {
      for (int k = 0; k < 6; k++) {
        P_temp[i][j] += F[i][k] * kalman.P[k][j];
      }
    }
  }
  
  for (int i = 0; i < 6; i++) {
    for (int j = 0; j < 6; j++) {
      float sum = 0;
      for (int k = 0; k < 6; k++) {
        sum += P_temp[i][k] * F[j][k];
      }
      kalman.P[i][j] = sum + kalman.Q[i][j];
    }
  }
}

void kalmanUpdate(KalmanState &kalman, float measuredX, float measuredY) {
  if (measuredX < 0 || measuredY < 0) return;

  float H[2][6] = {{1.0, 0, 0, 0, 0, 0},
                   {0, 1.0, 0, 0, 0, 0}};
  
  float z[2] = {measuredX, measuredY};
  float h[2] = {kalman.x, kalman.y};
  float y[2] = {z[0] - h[0], z[1] - h[1]};

  float S[2][2] = {{0}};
  for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 2; j++) {
      for (int k = 0; k < 6; k++) {
        S[i][j] += H[i][k] * kalman.P[k][j];
      }
    }
  }
  
  float S_temp[2][2] = {{0}};
  for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 2; j++) {
      for (int k = 0; k < 6; k++) {
        S_temp[i][j] += S[i][k] * H[j][k];
      }
      S[i][j] = S_temp[i][j] + kalman.R[i][j];
    }
  }

  float det = S[0][0] * S[1][1] - S[0][1] * S[1][0];
  if (abs(det) < 0.001) {
    #if DEBUG
    Serial.println("[DEBUG] Matrice S aproape singulară, skip update");
    #endif
    return;
  }

  float S_inv[2][2] = {{S[1][1] / det, -S[0][1] / det},
                       {-S[1][0] / det, S[0][0] / det}};

  float K[6][2] = {{0}};
  for (int i = 0; i < 6; i++) {
    for (int j = 0; j < 2; j++) {
      float sum = 0;
      for (int k = 0; k < 2; k++) {
        for (int l = 0; l < 6; l++) {
          sum += kalman.P[i][l] * H[k][l] * S_inv[k][j];
        }
      }
      K[i][j] = sum;
    }
  }

  kalman.x += K[0][0] * y[0] + K[0][1] * y[1];
  kalman.y += K[1][0] * y[0] + K[1][1] * y[1];
  kalman.vx += K[2][0] * y[0] + K[2][1] * y[1];
  kalman.vy += K[3][0] * y[0] + K[3][1] * y[1];
  kalman.ax += K[4][0] * y[0] + K[4][1] * y[1];
  kalman.ay += K[5][0] * y[0] + K[5][1] * y[1];

  float I_KH[6][6] = {{0}};
  for (int i = 0; i < 6; i++) {
    for (int j = 0; j < 6; j++) {
      float sum = 0;
      for (int k = 0; k < 2; k++) {
        sum += K[i][k] * H[k][j];
      }
      if (i == j) {
        I_KH[i][j] = 1.0 - sum;
      } else {
        I_KH[i][j] = -sum;
      }
    }
  }

  float P_new[6][6] = {{0}};
  for (int i = 0; i < 6; i++) {
    for (int j = 0; j < 6; j++) {
      for (int k = 0; k < 6; k++) {
        P_new[i][j] += I_KH[i][k] * kalman.P[k][j];
      }
    }
  }

  for (int i = 0; i < 6; i++) {
    for (int j = 0; j < 6; j++) {
      kalman.P[i][j] = P_new[i][j];
    }
  }
}

void updateBaseline() {
  unsigned long currentTime = millis();
  if (initialCalibration && currentTime < BASELINE_CALIBRATION_TIME) {
    for (uint8_t i = 0; i < NUM_SENSORS; i++) {
      if (sensors[i].distance > 0) {
        sensors[i].movingAverage[sensors[i].avgIndex] = sensors[i].distance;
        sensors[i].avgIndex = (sensors[i].avgIndex + 1) % 10;
        float sum = 0;
        for (uint8_t j = 0; j < 10; j++) sum += sensors[i].movingAverage[j];
        sensors[i].baseline = sum / 10.0;
      }
    }
    return;
  }

  if (initialCalibration) {
    initialCalibration = false;
    for (uint8_t i = 0; i < NUM_SENSORS; i++) {
      sensors[i].baseline = max(sensors[i].baseline, 100.0f);
    }
    lastBaselineUpdate = currentTime;
    return;
  }

  if (currentTime - lastBaselineUpdate >= BASELINE_UPDATE_INTERVAL && stableCounter <= 1) {
    for (uint8_t i = 0; i < NUM_SENSORS; i++) {
      if (sensors[i].distance > 0) {
        sensors[i].movingAverage[sensors[i].avgIndex] = sensors[i].distance;
        sensors[i].avgIndex = (sensors[i].avgIndex + 1) % 10;
        float sum = 0, mean = 0;
        for (uint8_t j = 0; j < 10; j++) sum += sensors[i].movingAverage[j];
        mean = sum / 10.0;
        float devSum = 0;
        for (uint8_t j = 0; j < 10; j++) devSum += pow(sensors[i].movingAverage[j] - mean, 2);
        sensors[i].deviation = sqrt(devSum / 10.0);

        if (sensors[i].deviation < DEVIATION_THRESHOLD && sensors[i].maxDistance > sensors[i].baseline) {
          sensors[i].baseline = max(sensors[i].maxDistance, 100.0f);
          #if DEBUG
          Serial.print("[DEBUG] Baseline actualizat pentru senzor ");
          Serial.print(i);
          Serial.print(": ");
          Serial.println(sensors[i].baseline, 1);
          #endif
        }
        sensors[i].maxDistance = MAX_DISTANCE;
      }
    }
    lastBaselineUpdate = currentTime;
  }
}

void calculatePosition(float* distances, float& x, float& y, float& confidence) {
  x = -1;
  y = -1;
  confidence = 0;

  uint8_t validSensors = 0;
  float totalWeight = 0;
  float weightedX = 0, weightedY = 0;

  for (uint8_t i = 0; i < NUM_SENSORS; i++) {
    if (distances[i] > MIN_DETECTION_DISTANCE && distances[i] < sensors[i].baseline - 20) {
      float sensorX, sensorY;
      float weight = (sensors[i].baseline - distances[i]) / sensors[i].baseline;
      weight = weight * weight;

      switch(i) {
        case 0: // Dreapta
          sensorX = ROOM_WIDTH - distances[i];
          sensorY = ROOM_HEIGHT / 2;
          break;
        case 1: // Stânga
          sensorX = distances[i];
          sensorY = ROOM_HEIGHT / 2;
          break;
        case 2: // Față
          sensorX = ROOM_WIDTH / 2;
          sensorY = distances[i];
          break;
        case 3: // Spate
          sensorX = ROOM_WIDTH / 2;
          sensorY = ROOM_HEIGHT - distances[i];
          break;
      }

      sensorX = constrain(sensorX, 0.0, (float)ROOM_WIDTH);
      sensorY = constrain(sensorY, 0.0, (float)ROOM_HEIGHT);

      weightedX += sensorX * weight;
      weightedY += sensorY * weight;
      totalWeight += weight;
      validSensors++;
    }
  }

  if (totalWeight > 0 && validSensors >= 2) {
    x = weightedX / totalWeight;
    y = weightedY / totalWeight;
    confidence = (float)validSensors / NUM_SENSORS;
  }
}

void transmitData() {
  unsigned long currentTime = millis();

  if (currentTime - lastTransmissionTime < MIN_TRANSMISSION_INTERVAL) return;

  uint8_t activeCount = 0;
  for (uint8_t i = 0; i < MAX_PEOPLE; i++) {
    if (people[i].active) activeCount++;
  }

  if (!dataChanged && activeCount == 0) return; // Nu transmitem dacă nu sunt schimbări

  String positions = activeCount > 0 ? "[" : "[]";
  String velocities = activeCount > 0 ? "[" : "[]";
  String confidences = activeCount > 0 ? "[" : "[]";

  if (activeCount > 0) {
    for (uint8_t i = 0; i < MAX_PEOPLE; i++) {
      if (people[i].active) {
        if (positions.length() > 2) {
          positions += ",";
          velocities += ",";
          confidences += ",";
        }
        positions += String(people[i].kalman.x, POSITION_PRECISION) + "," +
                    String(people[i].kalman.y, POSITION_PRECISION);
        velocities += String(people[i].kalman.vx, VELOCITY_PRECISION) + "," +
                     String(people[i].kalman.vy, VELOCITY_PRECISION);
        confidences += String(people[i].confidence, 1);
      }
    }
    positions += "]";
    velocities += "]";
    confidences += "]";
  }

  String json = "{\"c\":" + String(activeCount) +
                ",\"p\":" + positions +
                ",\"d\":[" + String(sensors[0].distance, DISTANCE_PRECISION) + "," +
                          String(sensors[1].distance, DISTANCE_PRECISION) + "," +
                          String(sensors[2].distance, DISTANCE_PRECISION) + "," +
                          String(sensors[3].distance, DISTANCE_PRECISION) + "]" +
                ",\"v\":" + velocities +
                ",\"f\":" + confidences +
                ",\"t\":" + String(currentTime) + "}";

  Serial.println(json);
  lastTransmissionTime = currentTime;
  dataChanged = false;
}

void debugPrint(const char* message) {
  #if DEBUG
  Serial.print("[DEBUG] ");
  Serial.println(message);
  #endif
}

void debugPrintPerson(uint8_t personIndex) {
  #if DEBUG
  Serial.print("[DEBUG] Persoana ");
  Serial.print(personIndex);
  Serial.print(": pos(");
  Serial.print(people[personIndex].kalman.x, 2);
  Serial.print(",");
  Serial.print(people[personIndex].kalman.y, 2);
  Serial.print(") vel(");
  Serial.print(people[personIndex].kalman.vx, 2);
  Serial.print(",");
  Serial.print(people[personIndex].kalman.vy, 2);
  Serial.print(") conf:");
  Serial.println(people[personIndex].confidence, 2);
  #endif
}

void detectPeople() {
  if (millis() - lastMeasureTime < SAMPLE_INTERVAL) return;

  bool motionDetected = false;
  uint8_t validSensors = 0;
  float distances[NUM_SENSORS];

  for (uint8_t i = 0; i < NUM_SENSORS; i++) {
    sensors[i].lastDistance = sensors[i].distance;
    float newDistance = measureDistance(trigPins[i], echoPins[i]);
    
    smoothSensorData(i, newDistance);
    sensors[i].distance = sensors[i].smoothedDistance;
    distances[i] = sensors[i].distance;
    
    if (sensors[i].distance > 0) {
      validSensors++;
      sensors[i].maxDistance = max(sensors[i].maxDistance, sensors[i].distance);
      
      if (sensors[i].lastDistance > 0 && 
          abs(sensors[i].distance - sensors[i].lastDistance) > MOTION_THRESHOLD) {
        motionDetected = true;
        sensors[i].stable = false;
      } else if (sensors[i].lastDistance > 0) {
        sensors[i].stable = true;
      }
    }
  }

  updateBaseline();
  lastMeasureTime = millis();

  if (validSensors >= 2) {
    float detectedX, detectedY, confidence;
    calculatePosition(distances, detectedX, detectedY, confidence);
    
    if (detectedX >= 0 && detectedY >= 0 && confidence > 0.3) {
      int bestPerson = -1;
      float minDistance = CLUSTER_DISTANCE_THRESHOLD;
      
      for (uint8_t i = 0; i < MAX_PEOPLE; i++) {
        if (people[i].active) {
          float dist = sqrt(pow(people[i].kalman.x - detectedX, 2) + 
                           pow(people[i].kalman.y - detectedY, 2));
          if (dist < minDistance) {
            minDistance = dist;
            bestPerson = i;
          }
        }
      }
      
      if (bestPerson == -1) {
        for (uint8_t i = 0; i < MAX_PEOPLE; i++) {
          if (!people[i].active) {
            bestPerson = i;
            people[i].active = true;
            people[i].kalman.x = detectedX;
            people[i].kalman.y = detectedY;
            people[i].kalman.vx = 0;
            people[i].kalman.vy = 0;
            people[i].kalman.ax = 0;
            people[i].kalman.ay = 0;
            people[i].kalman.lastUpdateTime = 0;
            break;
          }
        }
      }
      
      if (bestPerson >= 0) {
        kalmanPredict(people[bestPerson].kalman);
        kalmanUpdate(people[bestPerson].kalman, detectedX, detectedY);
        
        people[bestPerson].kalman.x = constrain(people[bestPerson].kalman.x, 0.0, (float)ROOM_WIDTH);
        people[bestPerson].kalman.y = constrain(people[bestPerson].kalman.y, 0.0, (float)ROOM_HEIGHT);
        
        people[bestPerson].confidence = confidence;
        people[bestPerson].lastSeenTime = millis();
        dataChanged = true;
        
        #if DEBUG
        debugPrintPerson(bestPerson);
        #endif
      }
    }
  }

  if (!motionDetected) {
    stableCounter++;
    if (stableCounter >= STABLE_COUNT) {
      unsigned long currentTime = millis();
      for (uint8_t i = 0; i < MAX_PEOPLE; i++) {
        if (people[i].active && (currentTime - people[i].lastSeenTime > 3000)) {
          people[i].active = false;
          dataChanged = true;
          #if DEBUG
          Serial.println("[DEBUG] Persoană inactivă din cauza timeout");
          #endif
        }
      }
      stableCounter = 0;
      for (uint8_t i = 0; i < NUM_SENSORS; i++) sensors[i].stable = true;
    }
  } else {
    stableCounter = 0;
  }

  bool shouldTransmit = false;
  if (dataChanged) shouldTransmit = true;
  if (motionDetected) shouldTransmit = true;
  
  uint8_t activeCount = 0;
  for (uint8_t i = 0; i < MAX_PEOPLE; i++) {
    if (people[i].active) activeCount++;
  }
  
  if (shouldTransmit && activeCount > 0) {
    transmitData();
  } else if (shouldTransmit && activeCount == 0 && dataChanged) {
    transmitData();
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  while (!Serial) delay(10);

  for (uint8_t i = 0; i < NUM_SENSORS; i++) {
    pinMode(trigPins[i], OUTPUT);
    pinMode(echoPins[i], INPUT);
    digitalWrite(trigPins[i], LOW);
    sensors[i].smoothedDistance = -1.0;
  }

  Serial.println("{\"status\":\"init\",\"device\":\"esp32_tracker\"}");
  lastBaselineUpdate = millis();
  lastTransmissionTime = millis();
}

void loop() {
  detectPeople();
}
