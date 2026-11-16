package com.playermodel;

import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.loading.FMLEnvironment;

@Mod(PlayerModelMod.MOD_ID)
public final class PlayerModelMod {
    public static final String MOD_ID = "player_model";

    public PlayerModelMod() {
        if (FMLEnvironment.dist == Dist.CLIENT) {
            com.playermodel.client.PlayerModelClient.init();
        }
    }
}
