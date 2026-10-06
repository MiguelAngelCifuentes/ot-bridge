package com.otbridge.api.repository;

import com.otbridge.api.entity.Threshold;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ThresholdRepository extends JpaRepository<Threshold, Long> {

    List<Threshold> findAllByOrderByIdAsc();

    List<Threshold> findByEnabledTrueOrderByIdAsc();
}
