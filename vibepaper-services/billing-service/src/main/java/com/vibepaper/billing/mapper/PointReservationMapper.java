package com.vibepaper.billing.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.vibepaper.billing.entity.PointReservation;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.time.OffsetDateTime;
import java.util.List;

public interface PointReservationMapper extends BaseMapper<PointReservation> {

    @Select("SELECT * FROM point_reservations WHERE status = 'pending' AND freeze_deadline < #{now} LIMIT 200 FOR UPDATE SKIP LOCKED")
    List<PointReservation> selectExpiredPending(@Param("now") OffsetDateTime now);
}
