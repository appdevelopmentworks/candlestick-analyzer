from analysis.scoring import total_score_from_hits, categorize_score

def test_total_score_from_hits_basic():
  hits=[{'fn':'CDLENGULFING','value':100},{'fn':'CDLENGULFING','value':-100},{'fn':'CDLKICKINGBYLENGTH','value':200}]
  s=total_score_from_hits(hits)
  assert -5 <= s <= 5


def test_categorize_score_labels():
  assert categorize_score(4) == ("Strong＋", "↑↑ Strong＋ (+4)")
  assert categorize_score(2) == ("Mild＋", "↑ Mild＋ (+2)")
  assert categorize_score(0) == ("Neutral", "Neutral (0)")
  assert categorize_score(-1) == ("Mild−", "↓ Mild− (-1)")
  assert categorize_score(-5) == ("Strong−", "↓↓ Strong− (-5)")
  assert categorize_score(None) == (None, "—")
