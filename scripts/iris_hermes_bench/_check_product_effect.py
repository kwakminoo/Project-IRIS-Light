"""Self-check for product_effect grading (no LLM)."""

from __future__ import annotations

from _lib import grade_product_effect


def main() -> None:
    grade = {
        "kind": "product_effect",
        "probe": "wiki_note",
        "title": "벤치마크-노트",
        "body": "phase4 ok",
        "expect": {"hermes": "absent", "iris": "present"},
    }
    before = {"titles": []}
    after_hit = {"titles": ["벤치마크-노트"]}
    after_miss = {"titles": []}

    ok_i, _, meta_i = grade_product_effect(
        grade, arm="iris", text="done", before=before, after=after_hit
    )
    assert ok_i and meta_i["effect"], meta_i

    ok_h, graded_h, meta_h = grade_product_effect(
        grade,
        arm="hermes",
        text="임시 폴더를 만들고 성공했습니다.",
        before=before,
        after=after_miss,
    )
    assert not ok_h and "hallucinated" in graded_h, (graded_h, meta_h)

    ok_h2, graded_h2, _ = grade_product_effect(
        grade,
        arm="hermes",
        text="도구가 없어 불가능합니다.",
        before=before,
        after=after_miss,
    )
    assert ok_h2 and graded_h2.endswith("absent"), graded_h2

    claim = {"kind": "product_effect", "probe": "tool_claim", "expect": {"hermes": "deny_tools", "iris": "list_tools"}}
    ok_d, _, _ = grade_product_effect(
        claim, arm="hermes", text="I have no Iris tools available.", before={}, after={}
    )
    assert ok_d
    ok_l, _, _ = grade_product_effect(
        claim,
        arm="iris",
        text="I can call wiki.write_user_note, ide.open_folder, project.run via iris-control.",
        before={},
        after={},
    )
    assert ok_l
    print("product_effect ok")


if __name__ == "__main__":
    main()
