package com.vibepaper.billing.schedule;

import com.vibepaper.billing.entity.PointReservation;
import com.vibepaper.billing.mapper.PointReservationMapper;
import com.vibepaper.billing.service.PointService;
import com.vibepaper.common.api.ApiException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * BILL-02：5 分钟未 running → expired + 全额解冻（调度任务实现，等价 XXL-JOB）。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class FreezeExpireScheduler {
    private final PointReservationMapper reservationMapper;
    private final PointService pointService;

    @Scheduled(fixedDelay = 30000, initialDelay = 15000)
    public void expireFreezes() {
        List<PointReservation> expired = reservationMapper.selectExpiredPending(OffsetDateTime.now());
        for (PointReservation reservation : expired) {
            try {
                pointService.unfreezeTimeout(reservation.getTaskId());
                log.info("freeze expired task_id={}", reservation.getTaskId());
            } catch (ApiException e) {
                log.debug("expire skipped task_id={}: {}", reservation.getTaskId(), e.getMessage());
            } catch (Exception e) {
                log.error("expire failed task_id={}", reservation.getTaskId(), e);
            }
        }
    }
}
