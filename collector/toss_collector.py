"""호환용 진입점.

실제 구현은 src/autoresearch/toss_collector.py 하나만 유지한다.
이 파일을 직접 실행해도 동일한 canonical Collector가 시작된다.
"""

from autoresearch.toss_collector import main


if __name__ == "__main__":
    main()
