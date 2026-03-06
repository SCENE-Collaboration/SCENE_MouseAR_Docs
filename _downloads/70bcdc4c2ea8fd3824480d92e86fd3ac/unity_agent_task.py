import logging
import time

import numpy as np

from mouse_ar.ctrl.dlc_client import DLCClient, DummyDLCClient
from mouse_ar.ctrl.touch_client import DummyTouchClient, TouchClient
from mouse_ar.ctrl.ttl_generator import TTLGenerator
from mouse_ar.tasks.unity_multibehavior_task import UnityMultibehaviorTask

LOG = logging.getLogger("UnityAgentTask")


class UnityAgentTask(UnityMultibehaviorTask):
    """
    Task class for Unity Agent-based tasks
    Inherits from UnityMultiBehaviorTask
    implements reading of inputs for agent
    """

    def __init__(
        self,
        teensy,
        env_path,
        monitor=1,
        fullscreen=1,
        fps=60.0,
        epochs=[1e5],
        epoch_trials=True,
        behavior_list: list[str] | None = None,
        reset_condition: str = "any",  # "any" or "all"
        env_kv_params: dict | None = None,
        env_params: dict | None = None,
        reward_size: int = 10,  # ms of reward signal
        use_dlc: bool = False,
        dlc_address: tuple[str, int] | str = ("localhost", 6000),
        use_photottl: bool = False,
        use_touch: bool = False,
        touch_address: tuple[str, int] | str = ("localhost", 7001),
        ttl_period_s: float = 5.0,
        ttl_half_cell_s: float = 0.050,
        ttl_preamble_halfcells: int = 2,
        ttl_start_delay: float = 2.0,
        use_perf_counter: bool = False,
        max_session_duration: float | None = None,  # max session duration in minutes
        **kwargs,
    ):
        """
        Constructor for UnityAgentTask
        Args:
            teensy(Teensy object): instance of teensy class
            env_path(str): path to the Unity environment
            agent_group(int): group ID for the agent (default: 0)
            monitor(int): monitor ID for the display (default: 1)
            fullscreen(int): fullscreen mode (default: 1)
            fps(float): frames per second (default: 60.0)
            epochs(list): list of epoch lengths (default: [1e5])
            epoch_trials(bool): whether to use epoch trials (default: True)
            behavior_list(list): list of behaviors to use (default: None)
            reset_condition(str): condition for resetting the environment (default: "any")
        """
        super().__init__(
            teensy,
            env_path,
            monitor=monitor,
            fullscreen=fullscreen,
            fps=fps,
            epochs=epochs,
            epoch_trials=epoch_trials,
            behavior_list=behavior_list,
            reset_condition=reset_condition,
            env_kv_params=env_kv_params,
            env_params=env_params,
            reward_size=reward_size,
            use_perf_counter=use_perf_counter,
            max_session_duration=max_session_duration,
            **kwargs,
        )

        self.use_dlc = use_dlc
        self.use_photottl = use_photottl
        self.dlc_address = dlc_address
        self.use_touch = use_touch
        self.touch_address = touch_address

        self.ttl_period_s = ttl_period_s
        self.ttl_half_cell_s = ttl_half_cell_s
        self.ttl_preamble_halfcells = ttl_preamble_halfcells
        self.ttl_start_delay = ttl_start_delay

        # DLC client parameters

        # apply filter only on data read by task to mimic the previous implementation
        self.dlc_apply_filter_onread = kwargs.get("dlc_apply_filter_onread", False)
        # apply filter on every received frame
        self.dlc_apply_filter = kwargs.get("dlc_apply_filter", False)
        # apply filter on every received frame in the DLC processor
        self.dlc_apply_filter_inprocessor = kwargs.get("dlc_apply_filter_inprocessor", False)

        # parameters for mapping DLC coordinates to normalized 0..1
        self.dlc_box_extents = kwargs.get("dlc_box_extents", (0, 0, 640, 480))
        self.dlc_flip_y = kwargs.get("dlc_flip_y", False)
        self.dlc_flip_x = kwargs.get("dlc_flip_x", False)
        self.dlc_rotate_90 = kwargs.get("dlc_rotate_90", False)

        # One Euro Filter parameters
        self.dlc_oneeuro_min_cutoff = kwargs.get("dlc_oneeuro_min_cutoff", None)
        self.dlc_oneeuro_beta = kwargs.get("dlc_oneeuro_beta", None)
        self.dlc_oneeuro_d_cutoff = kwargs.get("dlc_oneeuro_d_cutoff", None)

        # Interaction feedback parameters
        self.vibration_on_interaction = kwargs.get("vibration_on_interaction", False)
        self.vibration_step_duration = kwargs.get("vibration_step_duration", 200)
        self.use_tone_reward_cue = kwargs.get("use_tone_reward_cue", False)
        self.tone_duration = kwargs.get("tone_duration", 200)

        # Touch client parameters
        self.touch_tx_mode = kwargs.get("touch_tx_mode", "rate")
        self.touch_tx_hz = kwargs.get("touch_tx_hz", 60.0)
        self.touch_max_queue_packets = kwargs.get("touch_max_queue_packets", 256)
        self.touch_invert_y = kwargs.get("touch_invert_y", True)
        self.touch_speed_gain = kwargs.get("touch_speed_gain", 1.0)
        self.touch_min_cutoff = kwargs.get("touch_min_cutoff", 1.0)
        self.touch_beta = kwargs.get("touch_beta", 0.02)
        self.touch_jitter_px = kwargs.get("touch_jitter_px", 2.0)
        self.touch_merge_dist_norm = kwargs.get("touch_merge_dist_norm", 0.08)
        self.touch_vector_window_ms = kwargs.get("touch_vector_window_ms", 200)

        # DLC client for pose estimation
        if self.use_dlc:
            if isinstance(self.dlc_address, str):
                # if we dont pass address tuple use dummy client
                mode = "dummy"
                try:
                    m_type = self.dlc_address.split("_")[1]
                except:
                    m_type = "constant"
            else:
                mode = "socket"
            if mode == "dummy":
                self.dlc_client = DummyDLCClient(
                    mode=m_type,
                    normalize=True,
                    use_perf_counter=self.use_perf_counter,
                    apply_filter_always=self.dlc_apply_filter,
                    apply_filter_onread=self.dlc_apply_filter_onread,
                    flip_x=self.dlc_flip_x,
                    flip_y=self.dlc_flip_y,
                    rotate_90=self.dlc_rotate_90,
                    oneeuro_beta=self.dlc_oneeuro_beta,
                    oneeuro_min_cutoff=self.dlc_oneeuro_min_cutoff,
                    oneeuro_d_cutoff=self.dlc_oneeuro_d_cutoff,
                )
            else:
                self.dlc_client = DLCClient(
                    address=self.dlc_address,
                    use_perf_counter=self.use_perf_counter,
                    apply_filter_onread=self.dlc_apply_filter_onread,
                    apply_filter_always=self.dlc_apply_filter,
                    apply_filter_inprocessor=self.dlc_apply_filter_inprocessor,
                    box_extents=self.dlc_box_extents,
                    flip_x=self.dlc_flip_x,
                    flip_y=self.dlc_flip_y,
                    rotate_90=self.dlc_rotate_90,
                    oneeuro_beta=self.dlc_oneeuro_beta,
                    oneeuro_min_cutoff=self.dlc_oneeuro_min_cutoff,
                    oneeuro_d_cutoff=self.dlc_oneeuro_d_cutoff,
                    session_name=self.session_name,
                )
            self.dlc_client.start()

        # Generator of 8-bit TTL pulses for the photodiode sync
        if self.use_photottl:
            self.ttl_gen = TTLGenerator(
                period_s=self.ttl_period_s,
                half_cell_s=self.ttl_half_cell_s,
                preamble_halfcells=self.ttl_preamble_halfcells,
                start_delay_s=self.ttl_start_delay,
                start_counter=42,
                use_perf_counter=self.use_perf_counter,
            )

        # Touch client for touchscreen input
        if self.use_touch:
            if isinstance(self.touch_address, str):
                mode = "dummy"
                # if we dont pass address tuple use dummy client
                try:
                    m_type = self.touch_address.split("_")[1]
                except:
                    m_type = "constant"
            else:
                mode = "socket"
            if mode == "dummy":
                self.touch_client = DummyTouchClient(
                    mode=m_type,
                )
            else:
                self.touch_client = TouchClient(
                    host=self.touch_address[0],
                    port=self.touch_address[1],
                    use_perf_counter=self.use_perf_counter,
                    tx_mode=self.touch_tx_mode,
                    tx_hz=self.touch_tx_hz,
                    max_queue_packets=self.touch_max_queue_packets,
                    invert_y=self.touch_invert_y,
                    speed_gain=self.touch_speed_gain,
                    min_cutoff=self.touch_min_cutoff,
                    beta=self.touch_beta,
                    jitter_px=self.touch_jitter_px,
                    merge_dist_norm=self.touch_merge_dist_norm,
                    vector_window_ms=self.touch_vector_window_ms,
                )
            self.touch_client.start()

    def get_action_for(self, bname: str):
        """Return (kind, ndarray) for the given behavior (continuous|discrete)."""
        spec = self.behaviors[bname]["spec"]
        # LOG.info(f"Getting action for behavior: {bname} with spec: {spec}")
        if spec.action_spec.is_continuous():
            bare = self._canonicalize(bname)
            # TODO here we need to ensure correct naming of behaviors
            if bare == "TouchInput" and self.use_touch:
                return ("continuous", self._touch_action(spec))
            if bare == "DLCInput" and self.use_dlc:
                return ("continuous", self._dlc_action(spec))
            if bare == "TTLInput" and self.use_photottl:
                return ("continuous", self._ttl_action(spec))
            # default continuous behavior: zeros of right shape
            return (
                "continuous",
                np.zeros(spec.action_spec.continuous_size, dtype=np.float32),
            )
        else:
            branches = spec.action_spec.discrete_branches
            return ("discrete", np.zeros(len(branches), dtype=np.int32))

    def _on_kv_events(self, kv: dict):
        super()._on_kv_events(kv)
        contact_val = kv.get("hockey.player_contact")
        # TODO consider somehow setting the exact kvPrefix via parameters instead of hardcoding "hockey"
        # the kvPrefix need to be set in the Unity environment and match what we look for here in order to trigger the contact events
        if contact_val is not None:
            self.on_player_contact(contact_val == "1")

    def on_player_contact(self, contact: bool):
        """Called when puck contact starts (True) or ends (False)."""
        LOG.debug(f"Player-puck contact: {'start' if contact else 'end'}")
        if contact and self.vibration_on_interaction:
            self.give_vibration(self.vibration_step_duration)

    def give_reward(self, duration=10):
        super().give_reward(duration)
        if self.use_tone_reward_cue:
            self.give_tone(self.tone_duration)

    def get_info(self):
        """
        Returns:
            dictionary containing the information about session time, episode, episode_time
        """
        info = super().get_info()
        # TODO add more data if needed
        return info

    def get_data(self):
        data_dict = super().get_data()
        if self.use_dlc and self.dlc_client:
            data_dict.update(self.dlc_client.get_data())
        if self.use_touch and self.touch_client:
            data_dict.update(self.touch_client.get_data())
        if self.use_photottl and self.ttl_gen:
            data_dict.update(self.ttl_gen.get_data())
        # add more data if needed
        return data_dict

    def set_channel(self):
        """
        inherited from parent class interface
        Sets parameters to the Unity Environment
        """
        super().set_channel()
        # TODO add more parameters if needed

    # ---------- helpers to pack actions ----------

    @staticmethod
    def _pack_and_clip(vec, size):
        """Return float32 array of length 'size' from iterable 'vec' (truncate or zero-pad)."""
        a = np.zeros(int(size), dtype=np.float32)
        if size > 0 and vec:
            n = min(len(vec), int(size))
            a[:n] = np.asarray(vec[:n], dtype=np.float32)
        return a

    def _touch_action(self, spec):
        """
        Build action for Touch behavior.
        Expected fields from client.read_fields(): px, py, heading, speed01, vx, vy
        """
        size = spec.action_spec.continuous_size
        # default zeros
        empty = np.zeros(size, dtype=np.float32)
        empty[0] = 1.0  # default to border
        if not self.touch_client:
            return empty
        pkt = self.touch_client.read()
        if not pkt:
            return empty
        # preferred ordering (you can change to match your Unity agent):
        # [px, py, heading, speed01, ]
        vec = [
            pkt.get("px", 1.0),
            pkt.get("py", 0.0),
            pkt.get("heading", 0.0),
            pkt.get("speed01", 0.0),
        ]
        return self._pack_and_clip(vec, size)

    def _dlc_action(self, spec):
        """
        Build action for DLC behavior.
        DLC read() usually returns {"vals":[t, x, y, heading, head_angle], ...}
        """
        size = spec.action_spec.continuous_size
        empty = np.zeros(size, dtype=np.float32)
        if not self.dlc_client:
            return empty
        pkt = self.dlc_client.read()
        if not pkt:
            return empty
        vals = pkt.get("vals", [])
        # vals layout: [t, x, y, heading, head_angle] → drop time for action
        vec = []
        if len(vals) >= 2:
            # Use x, y, then heading/head_angle if present
            vec.extend(vals[1:])  # [x, y, heading, head_angle, ...]
        return self._pack_and_clip(vec, size)

    def _ttl_action(self, spec):
        """
        Build action for TTL behavior.
        First element is TTL (0/1). Remaining dims (if any) are zeros unless you want to repeat TTL.
        """
        size = spec.action_spec.continuous_size
        a = np.zeros(size, dtype=np.float32)
        if not self.ttl_gen or size <= 0:
            LOG.warning("TTL action: TTL generator not available or size <= 0")
            return a
        # ttl_vec = self.ttl_gen.action_tuple().ravel()  # [ttl]
        ttl_vec, *_ = self.ttl_gen.sample()
        a[0] = float(ttl_vec)
        # LOG.info(f"TTL action: {a}")
        # a[0] = float(ttl_vec[0])
        return a

    def get_params(self):
        params = super().get_params()
        params.update(
            {
                "use_dlc": self.use_dlc,
                "use_photottl": self.use_photottl,
                "use_touch": self.use_touch,
                "vibration_on_interaction": self.vibration_on_interaction,
                "vibration_step_duration": self.vibration_step_duration,
                "use_tone_reward_cue": self.use_tone_reward_cue,
                "tone_duration": self.tone_duration,
            }
        )

        if self.use_touch:
            params.update(self.touch_client.get_params())
        if self.use_dlc:
            params.update(self.dlc_client.get_params())
        if self.use_photottl:
            params.update(self.ttl_gen.get_params())
        return params

    def stop(self):
        """
        Stop the task and associated clients
        """
        super().stop()
        if self.use_dlc and self.dlc_client:
            self.dlc_client.close()
        if self.use_touch and self.touch_client:
            self.touch_client.stop()
        if self.use_photottl and self.ttl_gen:
            self.ttl_gen.stop()
