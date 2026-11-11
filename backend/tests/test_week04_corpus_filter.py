from scripts.week04_retrieval_comparison import usable

def test_directory_and_header_removed_without_dropping_financial_rows():
    assert not usable('第八节 财务报告................60')
    assert not usable('2026 年半年度报告全文')
    assert not usable('60')
    assert usable('营业收入（元）\n174,504,335,921.25')
    assert usable('董事会保证真实、准确、完整，不存在重大遗漏。')
