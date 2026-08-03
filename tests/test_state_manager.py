"""
状态管理器测试
"""
import pytest
from core.state_manager import StateManager


class TestStateManager:
    """状态管理器测试"""

    def setup_method(self):
        """每个测试方法前创建新的 StateManager"""
        self.manager = StateManager()

    def test_initial_state(self):
        """测试初始状态"""
        balance = self.manager.get_balance_state()
        assert balance['last_update'] is None
        assert balance['projects'] == []
        assert balance['summary'] == {}

        subscription = self.manager.get_subscription_state()
        assert subscription['last_update'] is None
        assert subscription['subscriptions'] == []

    def test_update_balance_state(self):
        """测试更新余额状态"""
        projects = [
            {'project': 'Test', 'success': True, 'credits': 100, 'threshold': 50, 'need_alarm': False},
            {'project': 'Test2', 'success': False, 'error': 'timeout', 'need_alarm': False},
        ]
        self.manager.update_balance_state(projects)

        state = self.manager.get_balance_state()
        assert state['last_update'] is not None
        assert len(state['projects']) == 2
        assert state['summary']['total'] == 2
        assert state['summary']['success'] == 1
        assert state['summary']['failed'] == 1

    def test_merge_balance_state(self):
        """测试部分刷新按项目名合并"""
        self.manager.update_balance_state([
            {'project': 'A', 'success': True, 'credits': 100, 'need_alarm': False},
            {'project': 'B', 'success': True, 'credits': 200, 'need_alarm': False},
        ])
        self.manager.merge_balance_state([
            {'project': 'B', 'success': False, 'error': 'timeout', 'need_alarm': False},
        ])

        state = self.manager.get_balance_state()
        assert len(state['projects']) == 2
        merged_b = next(p for p in state['projects'] if p['project'] == 'B')
        assert merged_b['success'] is False
        assert state['summary']['failed'] == 1

    def test_update_subscription_state(self):
        """测试更新订阅状态"""
        subscriptions = [
            {'name': 'Netflix', 'need_alert': True},
            {'name': 'Spotify', 'need_alert': False},
        ]
        self.manager.update_subscription_state(subscriptions)

        state = self.manager.get_subscription_state()
        assert state['last_update'] is not None
        assert len(state['subscriptions']) == 2
        assert state['summary']['total'] == 2
        assert state['summary']['need_alert'] == 1

    def test_update_subscription_state_none(self):
        """None 输入等价于空列表"""
        self.manager.update_subscription_state(None)
        state = self.manager.get_subscription_state()
        assert state['subscriptions'] == []
        assert state['summary']['total'] == 0

    def test_state_isolation(self):
        """测试更新不会修改外部列表"""
        projects = [{'project': 'A', 'success': True, 'need_alarm': False}]
        self.manager.update_balance_state(projects)

        # 修改外部列表不影响内部状态
        projects.append({'project': 'B', 'success': True, 'need_alarm': False})

        state = self.manager.get_balance_state()
        assert len(state['projects']) == 1

    def test_uptime_seconds(self):
        """运行时长非负且递增"""
        assert self.manager.uptime_seconds() >= 0


class TestConcurrentAccess:
    """多线程并发读写测试"""

    def setup_method(self):
        self.manager = StateManager()

    def test_concurrent_writes(self):
        """多线程同时写入不会导致数据损坏"""
        import concurrent.futures

        def write_balance(i):
            projects = [{'project': f'P{i}', 'success': True, 'need_alarm': False}]
            self.manager.update_balance_state(projects)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_balance, i) for i in range(50)]
            concurrent.futures.wait(futures)
            # 确保没有异常
            for f in futures:
                f.result()

        state = self.manager.get_balance_state()
        assert state['last_update'] is not None
        assert len(state['projects']) == 1  # 最后一个写入覆盖

    def test_concurrent_read_write(self):
        """读写并发不会抛异常"""
        import concurrent.futures

        self.manager.update_balance_state(
            [{'project': 'Init', 'success': True, 'need_alarm': False}]
        )

        errors = []

        def reader():
            try:
                for _ in range(100):
                    state = self.manager.get_balance_state()
                    assert 'projects' in state
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100):
                    self.manager.update_balance_state(
                        [{'project': f'W{i}', 'success': True, 'need_alarm': False}]
                    )
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = []
            for _ in range(3):
                futures.append(executor.submit(reader))
                futures.append(executor.submit(writer))
            concurrent.futures.wait(futures)

        assert errors == [], f"并发读写出错: {errors}"

    def test_concurrent_subscription_writes(self):
        """订阅状态多线程写入不死锁"""
        import concurrent.futures

        def write_sub(i):
            subs = [{'name': f'Sub{i}', 'need_alert': i % 2 == 0}]
            self.manager.update_subscription_state(subs)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_sub, i) for i in range(50)]
            concurrent.futures.wait(futures)
            for f in futures:
                f.result()

        state = self.manager.get_subscription_state()
        assert state['last_update'] is not None

    def test_snapshot_isolation(self):
        """快照返回后，后续写入不影响之前的快照"""
        self.manager.update_balance_state(
            [{'project': 'A', 'success': True, 'need_alarm': False}]
        )
        snapshot1 = self.manager.get_balance_state()

        self.manager.update_balance_state(
            [{'project': 'B', 'success': False, 'need_alarm': True}]
        )
        snapshot2 = self.manager.get_balance_state()

        assert snapshot1['projects'][0]['project'] == 'A'
        assert snapshot2['projects'][0]['project'] == 'B'


class TestSnapshotIndependence:
    """快照返回独立副本测试"""

    def setup_method(self):
        self.manager = StateManager()

    def test_balance_get_returns_independent_copies(self):
        """连续两次 get_balance_state 返回互不影响的副本"""
        self.manager.update_balance_state(
            [{'project': 'A', 'success': True, 'need_alarm': False}]
        )
        copy1 = self.manager.get_balance_state()
        copy2 = self.manager.get_balance_state()

        # 修改 copy1 不影响 copy2
        copy1['projects'].append({'project': 'INJECTED', 'success': False, 'need_alarm': True})
        copy1['summary']['total'] = 999

        assert len(copy2['projects']) == 1
        assert copy2['summary']['total'] == 1

    def test_subscription_get_returns_independent_copies(self):
        """连续两次 get_subscription_state 返回互不影响的副本"""
        self.manager.update_subscription_state(
            [{'name': 'Netflix', 'need_alert': True}]
        )
        copy1 = self.manager.get_subscription_state()
        copy2 = self.manager.get_subscription_state()

        # 修改 copy1 不影响 copy2
        copy1['subscriptions'].clear()
        copy1['summary']['total'] = 0

        assert len(copy2['subscriptions']) == 1
        assert copy2['summary']['total'] == 1

    def test_balance_mutation_does_not_affect_internal_state(self):
        """修改返回值不影响内部状态"""
        self.manager.update_balance_state(
            [{'project': 'A', 'success': True, 'need_alarm': False}]
        )
        returned = self.manager.get_balance_state()
        returned['projects'][0]['project'] = 'HACKED'

        fresh = self.manager.get_balance_state()
        assert fresh['projects'][0]['project'] == 'A'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
