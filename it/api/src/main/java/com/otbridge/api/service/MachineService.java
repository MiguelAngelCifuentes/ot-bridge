package com.otbridge.api.service;

import com.otbridge.api.dto.MachineDetailDto;
import com.otbridge.api.dto.MachineDto;
import com.otbridge.api.dto.PagedResponse;
import com.otbridge.api.entity.Machine;

import java.time.Instant;

public interface MachineService {

    PagedResponse<MachineDto> findAll(int page, int size);

    MachineDetailDto findById(Long id);

    void updateStatus(String name, boolean online, Instant ts);

    Machine requireByName(String name);
}
