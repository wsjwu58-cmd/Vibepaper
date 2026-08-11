package com.vibepaper.billing.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.vibepaper.billing.entity.PointAccount;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

public interface PointAccountMapper extends BaseMapper<PointAccount> {

    @Select("SELECT * FROM point_accounts WHERE user_id = #{userId} FOR UPDATE")
    PointAccount selectByUserIdForUpdate(@Param("userId") Long userId);
}
