"""Tests for cache manager: LRU eviction, stats, lock registry."""

from pathlib import Path


class TestCacheManager:
    def test_initial_stats(self, cache):
        stats = cache.stats()
        assert stats["used_bytes"] == 0
        assert stats["segment_count"] == 0
        assert stats["enabled"] is True

    def test_register_and_find_segment(self, cache):
        # Create a fake segment file
        seg_path = cache.segments_dir / "test_seg.ts"
        seg_path.write_bytes(b"x" * 1000)

        cache.register_segment("hash1", "720p", 0, str(seg_path), 1000)
        found = cache.get_segment_path("hash1", "720p", 0)
        assert found == str(seg_path)

    def test_missing_segment_returns_none(self, cache):
        assert cache.get_segment_path("nope", "720p", 0) is None

    def test_current_size(self, cache):
        cache.register_segment("h1", "720p", 0, "/fake", 5000)
        cache.register_segment("h1", "720p", 1, "/fake2", 3000)
        assert cache.current_size_bytes() == 8000

    def test_eviction(self, cache):
        # Set tiny limit
        cache.limit_bytes = 5000
        seg1 = cache.segments_dir / "s1.ts"
        seg2 = cache.segments_dir / "s2.ts"
        seg1.write_bytes(b"a" * 3000)
        seg2.write_bytes(b"b" * 3000)
        cache.register_segment("h1", "720p", 0, str(seg1), 3000)
        cache.register_segment("h2", "720p", 0, str(seg2), 3000)

        freed = cache.evict_if_needed()
        assert freed > 0
        assert cache.current_size_bytes() <= 5000

    def test_preload_not_evicted(self, cache):
        cache.limit_bytes = 1000
        seg = cache.segments_dir / "preload.ts"
        seg.write_bytes(b"x" * 2000)
        cache.register_segment("h1", "720p", 0, str(seg), 2000, is_preload=True)
        freed = cache.evict_if_needed()
        # Preload segments should NOT be evicted
        assert freed == 0
        assert cache.current_size_bytes() == 2000

    def test_clear(self, cache):
        seg = cache.segments_dir / "test.ts"
        seg.write_bytes(b"data")
        cache.register_segment("h", "720p", 0, str(seg), 4)
        freed = cache.clear()
        assert freed > 0
        assert cache.current_size_bytes() == 0

    def test_directories_exist(self, cache):
        assert cache.segments_dir.is_dir()
        assert cache.thumbnails_dir.is_dir()
        assert cache.sprites_dir.is_dir()
        assert cache.preload_dir.is_dir()


class TestLockRegistry:
    def test_subscribe_and_release(self):
        from face_detect.cache_manager import LockRegistry
        registry = LockRegistry()
        released = []
        registry.subscribe(lambda path: released.append(path))
        registry.request_release("/some/file.ts")
        assert released == ["/some/file.ts"]

    def test_multiple_subscribers(self):
        from face_detect.cache_manager import LockRegistry
        registry = LockRegistry()
        calls = []
        registry.subscribe(lambda p: calls.append(("a", p)))
        registry.subscribe(lambda p: calls.append(("b", p)))
        registry.request_release("/x")
        assert len(calls) == 2
