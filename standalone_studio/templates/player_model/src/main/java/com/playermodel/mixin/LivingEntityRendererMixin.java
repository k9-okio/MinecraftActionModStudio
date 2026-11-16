package com.playermodel.mixin;

import net.minecraft.client.model.EntityModel;
import net.minecraft.client.model.player.PlayerModel;
import net.minecraft.client.renderer.rendertype.RenderType;
import net.minecraft.client.renderer.entity.LivingEntityRenderer;
import net.minecraft.client.renderer.entity.state.AvatarRenderState;
import net.minecraft.client.renderer.entity.state.LivingEntityRenderState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(LivingEntityRenderer.class)
public abstract class LivingEntityRendererMixin {
    @Shadow
    public abstract EntityModel<?> getModel();

    @Inject(method = "getRenderType(Lnet/minecraft/client/renderer/entity/state/LivingEntityRenderState;ZZZ)Lnet/minecraft/client/renderer/rendertype/RenderType;",
            at = @At("HEAD"), cancellable = true)
    private void player_model$hideVanilla(LivingEntityRenderState state, boolean bodyVisible,
                                          boolean translucent, boolean glowing,
                                          CallbackInfoReturnable<RenderType> cir) {
        if (state instanceof AvatarRenderState && getModel() instanceof PlayerModel) {
            // LivingEntityRenderer defers model submission. Returning no render type here
            // removes only the vanilla player body while keeping its render layers intact.
            cir.setReturnValue(null);
        }
    }
}
