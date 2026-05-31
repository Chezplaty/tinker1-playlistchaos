from typing import Dict, List, Optional, Tuple

Song = Dict[str, object]
PlaylistMap = Dict[str, List[Song]]

DEFAULT_PROFILE = {
    "name": "Default",
    "hype_min_energy": 7,
    "chill_max_energy": 3,
    "favorite_genre": "rock",
    "include_mixed": True,
}


def normalize_title(title: str) -> str:
    """Normalize a song title for comparisons."""
    if not isinstance(title, str):
        return ""
    return title.strip()


def normalize_artist(artist: str) -> str:
    """Normalize an artist name for comparisons."""
    if not artist:
        return ""
    return artist.strip().lower()


def normalize_genre(genre: str) -> str:
    """Normalize a genre name for comparisons."""
    return genre.lower().strip()


def normalize_song(raw: Song) -> Song:
    """Return a normalized song dict with expected keys."""
    title = normalize_title(str(raw.get("title", "")))
    artist = normalize_artist(str(raw.get("artist", "")))
    genre = normalize_genre(str(raw.get("genre", "")))
    energy = raw.get("energy", 0)

    if isinstance(energy, str):
        try:
            energy = int(energy)
        except ValueError:
            energy = 0

    tags = raw.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    return {
        "title": title,
        "artist": artist,
        "genre": genre,
        "energy": energy,
        "tags": tags,
    }


# Mood is scored on a 0..1 scale: Chill = 0.0, Mixed = 0.5, Hype = 1.0.
CHILL_SCORE = 0.0
MIXED_SCORE = 0.5
HYPE_SCORE = 1.0

# How much each factor contributes to the blended mood score.
ENERGY_WEIGHT = 0.7
GENRE_WEIGHT = 0.3

# Final bands for the blended score: >= HYPE_CUTOFF is Hype, <= CHILL_CUTOFF is
# Chill, anything in between is Mixed. With the 0.7/0.3 split these cutoffs let
# genre tip an energy-ambiguous (Mixed-energy) song up or down, while a clearly
# hype or chill energy still wins on its own.
HYPE_CUTOFF = 0.6
CHILL_CUTOFF = 0.4

# Which mood each genre leans toward. Unlisted genres ("other", anything new)
# fall back to the neutral middle.
GENRE_MOODS = {
    "rock": HYPE_SCORE,
    "pop": HYPE_SCORE,
    "electronic": HYPE_SCORE,
    "punk": HYPE_SCORE,
    "party": HYPE_SCORE,
    "lofi": CHILL_SCORE,
    "ambient": CHILL_SCORE,
    "jazz": MIXED_SCORE,
}


def energy_mood_score(energy: object, profile: Dict[str, object]) -> float:
    """Score a song's energy on the 0 (chill) .. 1 (hype) mood scale."""
    hype_min_energy = profile.get("hype_min_energy", 7)
    chill_max_energy = profile.get("chill_max_energy", 3)

    if energy >= hype_min_energy:
        return HYPE_SCORE
    if energy <= chill_max_energy:
        return CHILL_SCORE
    return MIXED_SCORE


def genre_mood_score(
    genre: str,
    genre_moods: Optional[Dict[str, float]] = None,
) -> float:
    """Score a song's genre on the 0 (chill) .. 1 (hype) mood scale.

    Uses the supplied genre->mood map (e.g. the user's edited one) and falls
    back to the built-in defaults when none is given.
    """
    if genre_moods is None:
        genre_moods = GENRE_MOODS
    return genre_moods.get(genre, MIXED_SCORE)


def classify_song(song: Song, profile: Dict[str, object]) -> str:
    """Return a mood label from a weighted blend of energy and genre.

    score = 0.7 * energy_score + 0.3 * genre_score, then bucketed into a band.
    """
    energy = song.get("energy", 0)
    genre = song.get("genre", "")

    # Prefer the user's edited genre map (kept on the profile) when present.
    genre_moods = profile.get("genre_moods") or GENRE_MOODS

    score = (
        ENERGY_WEIGHT * energy_mood_score(energy, profile)
        + GENRE_WEIGHT * genre_mood_score(genre, genre_moods)
    )

    if score >= HYPE_CUTOFF:
        return "Hype"
    if score <= CHILL_CUTOFF:
        return "Chill"
    return "Mixed"


def build_playlists(songs: List[Song], profile: Dict[str, object]) -> PlaylistMap:
    """Group songs into playlists based on mood and profile."""
    playlists: PlaylistMap = {
        "Hype": [],
        "Chill": [],
        "Mixed": [],
    }

    for song in songs:
        normalized = normalize_song(song)
        mood = classify_song(normalized, profile)
        normalized["mood"] = mood
        playlists[mood].append(normalized)

    return playlists


def merge_playlists(a: PlaylistMap, b: PlaylistMap) -> PlaylistMap:
    """Merge two playlist maps into a new map."""
    merged: PlaylistMap = {}
    for key in set(list(a.keys()) + list(b.keys())):
        merged[key] = a.get(key, [])
        merged[key].extend(b.get(key, []))
    return merged


def compute_playlist_stats(playlists: PlaylistMap) -> Dict[str, object]:
    """Compute statistics across all playlists."""
    all_songs: List[Song] = []
    for songs in playlists.values():
        all_songs.extend(songs)

    hype = playlists.get("Hype", [])
    chill = playlists.get("Chill", [])
    mixed = playlists.get("Mixed", [])

    # Hype ratio is hype songs as a fraction of the whole library.
    total = len(all_songs)
    hype_ratio = len(hype) / total if total > 0 else 0.0

    avg_energy = 0.0
    if all_songs:
        total_energy = sum(song.get("energy", 0) for song in hype)
        avg_energy = total_energy / len(all_songs)

    top_artist, top_count = most_common_artist(all_songs)

    return {
        "total_songs": len(all_songs),
        "hype_count": len(hype),
        "chill_count": len(chill),
        "mixed_count": len(mixed),
        "hype_ratio": hype_ratio,
        "avg_energy": avg_energy,
        "top_artist": top_artist,
        "top_artist_count": top_count,
    }


def most_common_artist(songs: List[Song]) -> Tuple[str, int]:
    """Return the most common artist and count."""
    counts: Dict[str, int] = {}
    for song in songs:
        artist = str(song.get("artist", ""))
        if not artist:
            continue
        counts[artist] = counts.get(artist, 0) + 1

    if not counts:
        return "", 0

    items = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return items[0]


def search_songs(
    songs: List[Song],
    query: str,
    field: str = "artist",
) -> List[Song]:
    """Return songs matching the query on a given field."""
    if not query:
        return songs

    q = query.lower().strip()
    filtered: List[Song] = []

    for song in songs:
        value = str(song.get(field, "")).lower()
        # Match when the query appears inside the field (so partial searches
        # work), not when the field appears inside the query.
        if value and q in value:
            filtered.append(song)

    return filtered

#lucky_pick considers mixed songs as well
def lucky_pick(
    playlists: PlaylistMap,
    mode: str = "any",
) -> Optional[Song]:
    """Pick a song from the playlists according to mode."""
    if mode == "hype":
        songs = playlists.get("Hype", [])
    elif mode == "chill":
        songs = playlists.get("Chill", [])
    elif mode == "mixed":
        songs = playlists.get("Mixed", [])
    else:
        songs = (
            playlists.get("Hype", [])
            + playlists.get("Chill", [])
            + playlists.get("Mixed", [])
        )

    return random_choice_or_none(songs)

#added guardrail against empty list
def random_choice_or_none(songs: List[Song]) -> Optional[Song]:
    """Return a random song or None."""
    import random

    if not songs:
        return None

    return random.choice(songs)


def history_summary(history: List[Song]) -> Dict[str, int]:
    """Return a summary of moods seen in the history."""
    counts = {"Hype": 0, "Chill": 0, "Mixed": 0}
    for song in history:
        mood = song.get("mood", "Mixed")
        if mood not in counts:
            counts["Mixed"] += 1
        else:
            counts[mood] += 1
    return counts
