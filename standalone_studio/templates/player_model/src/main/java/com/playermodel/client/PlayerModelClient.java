package com.playermodel.client;

import net.minecraft.client.model.geom.ModelLayerLocation;
import net.minecraft.resources.Identifier;
import net.minecraft.world.entity.player.PlayerModelType;
import net.minecraftforge.client.event.EntityRenderersEvent;

import java.util.EnumSet;

public final class PlayerModelClient {
    public static final ModelLayerLocation WIDE_LAYER = new ModelLayerLocation(
            Identifier.fromNamespaceAndPath("player_model", "player"), "wide");
    public static final ModelLayerLocation SLIM_LAYER = new ModelLayerLocation(
            Identifier.fromNamespaceAndPath("player_model", "player"), "slim");

    private PlayerModelClient() {
    }

    public static void init() {
        EntityRenderersEvent.RegisterLayerDefinitions.BUS.addListener(event -> {
            event.registerLayerDefinition(WIDE_LAYER, () -> CustomPlayerModel.createLayer(false));
            event.registerLayerDefinition(SLIM_LAYER, () -> CustomPlayerModel.createLayer(true));
        });
        EntityRenderersEvent.AddLayers.BUS.addListener(PlayerModelClient::addLayers);
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private static void addLayers(EntityRenderersEvent.AddLayers event) {
        for (PlayerModelType type : EnumSet.allOf(PlayerModelType.class)) {
            var playerRenderer = event.getPlayerRenderer(type);
            if (playerRenderer instanceof net.minecraft.client.renderer.entity.LivingEntityRenderer renderer) {
                renderer.addLayer(new CustomPlayerLayer(renderer, event.getEntityModels()));
            }

            var mannequinRenderer = event.getMannequinRenderer(type);
            if (mannequinRenderer instanceof net.minecraft.client.renderer.entity.LivingEntityRenderer renderer) {
                renderer.addLayer(new CustomPlayerLayer(renderer, event.getEntityModels()));
            }
        }
    }
}
