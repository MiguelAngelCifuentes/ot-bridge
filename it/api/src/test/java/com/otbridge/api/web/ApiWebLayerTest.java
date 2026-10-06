package com.otbridge.api.web;

import com.otbridge.api.controller.AlarmsController;
import com.otbridge.api.dto.AlarmDto;
import com.otbridge.api.dto.PagedResponse;
import com.otbridge.api.exception.NotFoundException;
import com.otbridge.api.service.AlarmService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Capa web: filtro de API key y traduccion de errores a 4xx (nunca 500 por culpa del cliente). */
@WebMvcTest(AlarmsController.class)
@TestPropertySource(properties = {"api.security.enabled=true", "api.keys.read=read-key", "api.keys.operator=op-key"})  // gitleaks:allow (claves ficticias de test)
class ApiWebLayerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private AlarmService alarmService;

    @Test
    void missingOrWrongKeyIs401() throws Exception {
        mvc.perform(get("/api/alarms")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/alarms").header("X-API-Key", "nope")).andExpect(status().isUnauthorized());
    }

    @Test
    void readKeyCanGetButNotWrite() throws Exception {
        when(alarmService.search(any(), any(), any(), anyInt(), anyInt()))
                .thenReturn(new PagedResponse<AlarmDto>(List.of(), 0, 20, 0, 0));
        mvc.perform(get("/api/alarms").header("X-API-Key", "read-key")).andExpect(status().isOk());
        mvc.perform(post("/api/alarms/1/acknowledge").header("X-API-Key", "read-key")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"ackBy\":\"x\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void operatorKeyCanWrite() throws Exception {
        mvc.perform(post("/api/alarms/1/acknowledge").header("X-API-Key", "op-key")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"ackBy\":\"operador\"}"))
                .andExpect(status().isOk());
    }

    @Test
    void clientErrorsAreNot500() throws Exception {
        mvc.perform(get("/api/alarms").param("state", "FOO").header("X-API-Key", "read-key"))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/alarms/abc").header("X-API-Key", "read-key")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/nope").header("X-API-Key", "read-key")).andExpect(status().isNotFound());
        mvc.perform(post("/api/alarms/1/acknowledge").header("X-API-Key", "op-key")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"ackBy\":\"\"}"))
                .andExpect(status().isBadRequest());
        mvc.perform(delete("/api/alarms/1")
                        .header("X-API-Key", "op-key"))
                .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void notFoundHasJsonBody() throws Exception {
        when(alarmService.findById(99L)).thenThrow(new NotFoundException("Alarma no encontrada: 99"));
        mvc.perform(get("/api/alarms/99").header("X-API-Key", "read-key"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404));
    }
}
