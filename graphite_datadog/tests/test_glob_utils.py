# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific lanbg_guage governing permissions and
# limitations under the License.

from __future__ import print_function

from collections import defaultdict
import re
import unittest

from graphite_datadog import glob_utils


class TestGlobUtilsInternals(unittest.TestCase):
    def test_is_graphite_glob(self):
        is_glob = ["a*", "a.b*", "a.b?", "a.b[a-z]?", "a{b,c,d}.a", "a.*.a", "{a}"]
        for x in is_glob:
            self.assertTrue(glob_utils._is_graphite_glob(x))

        not_glob = ["a.a", "a-z"]
        for x in not_glob:
            self.assertFalse(glob_utils._is_graphite_glob(x))

    def test_is_valid_glob(self):
        valid_glob = ["a", "a.b", "{a}.b", "{a,{b,c}}.d", "{a,b}.{c,d}.e"]
        for x in valid_glob:
            self.assertTrue(glob_utils._is_valid_glob(x))

        invalid_glob = [
            "{",
            "{{}",
            "{}}",
            "}{",
            "}{}",
            "{a.}.b",
            "{a,{.b,c}}.d",
            "{a,b.}.{.c,d}.e",
        ]
        for x in invalid_glob:
            self.assertFalse(glob_utils._is_valid_glob(x))

    def test_glob_to_regex(self):
        def filter_metrics(metrics, glob):
            print(glob + "   ===>   " + glob_utils.glob_to_regex(glob))
            glob_re = re.compile(glob_utils.glob_to_regex(glob))
            return list(filter(glob_re.match, metrics))

        scenarii = [
            (["a", "a.b", "a.cc"], "a.*", ["a.b", "a.cc"]),
            (["a.b", "a.cc"], "a.?", ["a.b"]),
            (["a.b", "a.cc", "y.z"], "?.*", ["a.b", "a.cc", "y.z"]),
            (["a.bd", "a.cd", "y.z"], "?.{b,c}?", ["a.bd", "a.cd"]),
            (["a.b_", "a.0_", "a.1_"], "?.[0-9]?", ["a.0_", "a.1_"]),
            (["a.b", "a.b.c", "a.x.y"], "a.*.*", ["a.b.c", "a.x.y"]),
            (["a.b", "a.b.c", "a.x.y"], "a.{b,x}.*", ["a.b.c", "a.x.y"]),
            (["a.b", "a.b.c", "a.x.y"], "a.{b,x}.{c,y}", ["a.b.c", "a.x.y"]),
            (
                ["a.b", "a.b.c", "a.x.y", "a.x.z"],
                "a.{b,x}.{c,{y,z}}",
                ["a.b.c", "a.x.y", "a.x.z"],
            ),
            # issue 240
            (
                [
                    "fib.bar",
                    "fib.bart",
                    "foo.baaa",
                    "foo.bar",
                    "foo.bart",
                    "foo.bli",
                    "foo.blo",
                ],
                "foo.{bar*,bli}",
                ["foo.bar", "foo.bart", "foo.bli"],
            ),
            # issue 290
            (
                [
                    "fib.bar.la",
                    "fib.bart.la",
                    "foo.baaa.la",
                    "foo.bar.la",
                    "foo.bart.la",
                    "foo.blit.la",
                    "foo.blo.la",
                ],
                "foo.{bar*,bli*}.la",
                ["foo.bar.la", "foo.bart.la", "foo.blit.la"],
            ),
        ]
        for (full, glob, filtered) in scenarii:
            self.assertEqual(filtered, filter_metrics(full, glob))


if __name__ == "__main__":
    unittest.main()
