FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B -q dependency:go-offline
COPY src ./src
# Los tests unitarios (JUnit + MockMvc, sin BD ni broker) son parte del build: si fallan, no hay imagen
RUN mvn -B -q package

FROM eclipse-temurin:21-jre
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /build/target/plant-api-0.0.1-SNAPSHOT.jar app.jar
RUN useradd --system --uid 10003 api
USER api
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
