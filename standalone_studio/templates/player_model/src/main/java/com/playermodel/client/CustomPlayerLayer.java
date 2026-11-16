package com.playermodel.client;

import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.model.EntityModel;
import net.minecraft.client.model.geom.EntityModelSet;
import net.minecraft.client.model.player.PlayerModel;
import net.minecraft.client.renderer.SubmitNodeCollector;
import net.minecraft.client.renderer.entity.RenderLayerParent;
import net.minecraft.client.renderer.entity.layers.RenderLayer;
import net.minecraft.client.renderer.entity.state.AvatarRenderState;
import net.minecraft.resources.Identifier;
import net.minecraft.world.entity.player.PlayerModelType;

public final class CustomPlayerLayer extends RenderLayer<AvatarRenderState, PlayerModel> {
    private final CustomPlayerModel wideModel;
    private final CustomPlayerModel slimModel;
    private final AnimationLibrary animations;

    public CustomPlayerLayer(RenderLayerParent<AvatarRenderState, PlayerModel> parent, EntityModelSet modelSet) {
        super(parent);
        this.animations = AnimationLibrary.load();
        this.wideModel = new CustomPlayerModel(modelSet.bakeLayer(PlayerModelClient.WIDE_LAYER), animations);
        this.slimModel = new CustomPlayerModel(modelSet.bakeLayer(PlayerModelClient.SLIM_LAYER), animations);
    }

    @Override
    public void submit(PoseStack poseStack, SubmitNodeCollector collector, int light,
                       AvatarRenderState state, float limbSwing, float limbSwingAmount) {
        CustomPlayerModel model = state.skin.model() == PlayerModelType.SLIM ? slimModel : wideModel;
        model.setupAnim(state);
        Identifier texture = state.skin.body().texturePath();
        renderColoredCutoutModel(model, texture, poseStack, collector, light, state, -1, 0);
    }
}
