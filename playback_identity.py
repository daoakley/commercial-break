"""Frame admission only: no ad detection or interpretation of cached app memory.

The transport session is the TV agent instance plus navigation generation. It
is deliberately not called a YouTube playback ID or a confirmed show identity.
"""
from dataclasses import dataclass, field


def navigation_session(value):
    parts = value.rsplit('-', 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1])
    return value, None


@dataclass
class PlaybackIdentity:
    app: str = ''
    session: str = ''
    channel: str = ''
    title: str = ''
    epoch: int = 0
    ticket: int = 0
    sequence: int = 0
    retired_sessions: set = field(default_factory=set)
    retired_agents: set = field(default_factory=set)
    initialized: bool = False
    observed_unix: float = 0

    def admit(self, context, observed_unix=0):
        """Call under the detector registry lock; returns accepted, reset reason."""
        app = str(context.get('app') or '')
        session = str(context.get('session') or '')
        channel = str(context.get('channel') or '')
        title = str(context.get('title') or '')
        sequence = context.get('frame_sequence')
        if sequence not in (None, ''):
            if isinstance(sequence, bool) or not str(sequence).isdigit() or not 0 < int(sequence) < 2**63:
                return False, 'invalid frame sequence'
            sequence = int(sequence)
        else:
            sequence = 0
        agent, navigation = navigation_session(session)
        old_agent, old_navigation = navigation_session(self.session)
        if self.initialized:
            if self.session and not session:
                return False, 'missing playback session'
            if session != self.session:
                if session in self.retired_sessions or agent in self.retired_agents:
                    return False, 'retired playback session'
                if agent == old_agent and old_navigation is not None and navigation is not None and navigation < old_navigation:
                    return False, 'older navigation generation'
            if agent == old_agent and self.sequence and sequence <= self.sequence:
                return False, 'older or missing frame sequence'
        reason = ''
        if self.initialized:
            if session and self.session and session != self.session:
                reason = 'navigation/session changed'
            elif self.app != app:
                reason = 'app changed'
            elif channel and channel != self.channel:
                reason = 'channel changed'
            elif title and title != self.title:
                reason = 'title changed'
        if reason:
            self.epoch += 1
            if self.session and session != self.session:
                self.retired_sessions.add(self.session)
                if agent != old_agent:
                    self.retired_agents.add(old_agent)
            self.channel = self.title = ''
        self.app, self.session = app, session
        if channel: self.channel = channel
        if title: self.title = title
        self.sequence = sequence
        self.ticket += 1
        self.initialized = True
        self.observed_unix = observed_unix
        return True, reason

    def snapshot(self):
        return dict(epoch=self.epoch, transport_session=self.session or None,
                    observed_unix=self.observed_unix or None, frame_sequence=self.sequence or None,
                    session_source='tv_agent_navigation' if self.session else 'unknown',
                    source_app=self.app or None,
                    channel=dict(name=self.channel or None,
                                 source='supplied_metadata' if self.channel else 'unknown'),
                    show=dict(name=self.title or None,
                              source='supplied_metadata' if self.title else 'unknown'),
                    youtube_playback_id=None)
