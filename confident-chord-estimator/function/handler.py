#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import numpy as np
import json
import madmom
from scipy.linalg import circulant
import itertools
import os
import os.path
import requests
from collections import defaultdict
from hiddini import HMMTemplateCosSim
# import io


# Config
block_size = 8192
step_size = 4410
samplerate = 44100
type_templates = np.array([[1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0],
                           [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0],
                           [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0],
                           [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1],
                           [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0]])
chord_types = ['maj', 'min', '7', 'maj7', 'min7']
chromas = ['A', 'Bb', 'B', 'C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab']
chord_self_prob = 0.1


def squash_timed_labels(start_times, end_times, labels):
    centre_times = np.mean((start_times, end_times), axis=0)
    centre_crossovers = centre_times[:-1] + np.diff(centre_times) / 2
    disjoint_starts = np.hstack((centre_times[0], centre_crossovers))
    disjoint_ends = np.hstack((centre_crossovers, centre_times[-1]))
    change_points = labels[1:] != labels[:-1]
    return disjoint_starts[np.hstack(([True],change_points))], disjoint_ends[np.hstack((change_points, [True]))], labels[np.hstack(([True],change_points))]


class MadMomDeepChromaExtractor:
    def __init__(self, samplerate, frame_size, step_size):
        self.samplerate = samplerate
        self.frame_size = frame_size
        self.step_size = step_size
        if samplerate != 44100 or frame_size != 8192 or step_size != 4410:
            raise ValueError('Parameter values not supported')
        self.frame_cutter = madmom.audio.FramedSignalProcessor(frame_size=frame_size, hop_size=step_size)
        self.extractor = madmom.audio.chroma.DeepChromaProcessor(num_channels=1)
    
    def get_frame_times(self, chromagram):
        start_times = self.step_size / self.samplerate * np.arange(len(chromagram)) - self.frame_size/(2*self.samplerate)
        return start_times, start_times+self.frame_size/self.samplerate

    def __call__(self, audio_file):
        signal = madmom.audio.Signal(audio_file, num_channels=1)
        duration = signal.num_samples / signal.sample_rate
        framed_signal = self.frame_cutter(signal)
        frame_spls = framed_signal.sound_pressure_level()
        chromagram = self.extractor(signal)
        chromagram = np.roll(chromagram, 3, axis=1)
        return chromagram, self.get_frame_times(chromagram), duration, frame_spls


class ChordEstimator:
    def __init__(self, chromas, chord_types, type_templates, chroma_extractor, chord_self_prob):
        self.chords = np.array([''.join(x) for x in itertools.product(chromas, chord_types)])
        self.chroma_extractor = chroma_extractor
        chord_templates = np.dstack([circulant(i) for i in type_templates]).reshape(len(chromas), -1).T
        num_chords = len(self.chords)
        trans_prob = np.full((num_chords, num_chords), (1-chord_self_prob)/(num_chords-1))
        np.fill_diagonal(trans_prob, chord_self_prob)
        self.hmm = HMMTemplateCosSim(chord_templates, trans_prob, np.full(num_chords, 1/num_chords))
    
    def __call__(self, audio_file):
        chromagram, (start_times, end_times), duration, frame_spls = self.chroma_extractor(audio_file)
        hmm_smoothed_state_indices, _, confidence = self.hmm.decode_with_PPD(chromagram.T)
        squashed_start_times, squashed_end_times, squashed_chord_labels = squash_timed_labels(start_times, end_times, self.chords[hmm_smoothed_state_indices])
        return squashed_start_times, squashed_end_times, squashed_chord_labels, confidence, duration, frame_spls
 

cp = MadMomDeepChromaExtractor(samplerate, block_size, step_size)
hmm = ChordEstimator(chromas, chord_types, type_templates, cp, chord_self_prob)


def handle(audio_content):
    """handle a request to the function
    Args:
        audio_content (bytes): audio bytestream
    """
    audio_path = os.getenv('Http_Path', '').lstrip('/')
    if not audio_path:
        audio_path = 'audio'
    try:
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    except FileNotFoundError:
        pass
    with open(audio_path, 'wb') as f:
        f.write(audio_content)
    start_times, end_times, chord_labels, confidence, duration, frame_spls = hmm(audio_path)
    # start_times, end_times, chord_labels, confidence, duration, frame_spls = hmm(io.BytesIO(audio_content))
    response = {'confidence': confidence, 'duration': duration, 'chordSequence': [], 'chordRatio': defaultdict(int)}
    for start, end, label in zip(start_times, end_times, chord_labels):
        response['chordSequence'].append({'start': start, 'end': end, 'label': label})
        response['chordRatio'][label] += end - start
    response['chordRatio'].update({k: v/end for k, v in response['chordRatio'].items()})
    response['distinctChords'] = len(response['chordRatio'])
    return json.dumps(response)
