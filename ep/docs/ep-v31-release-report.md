# EP v3.1 release evaluation

11 November 2026, Asia/Calcutta.

**Release classification: ENGINEERING READY** for the measured bounded standalone advisory evidence workflow. **Not PILOT READY** for physical-damage assessment: independent condition labels and physical-identity validation are unavailable.

This report is generated from private execution ledgers and verified artifacts. Physical damage ground truth is unavailable; no detection accuracy is claimed.

| Metric | Frozen EP v3 | EP v3.1 |
|---|---:|---:|
| Total current-collection before/after pairs | 17 | 17 |
| Comparable pairs | 6 | 7 |
| Inconclusive pairs | 10 | 10 |
| Failed pairs | 1 | 0 |
| Exact-repeat failures / 17 | 3 | 0 |
| Exact-repeat appearance proposal jobs | 0 | 0 |
| Different-object confirmed physical identities / 5 | 0 | 0 |
| Median process wall time per real pair (seconds) | 21.914 | 12.628 |
| Peak CUDA allocated, real pairs (bytes) | 501436416 | 501436416 |
| Peak CUDA reserved, real pairs (bytes) | 698351616 | 698351616 |
| Peak host working set, real pairs (bytes) | 1760808960 | 1781047296 |
| Damage precision / recall / F1 / localization accuracy | N/A | N/A |
| Alignment validity | Internal gates pass; GT NOT VERIFIED | Internal gates pass; GT NOT VERIFIED |

Wall time includes interpreter/model startup, verified model reads, inference, artifacts and report serialization. It is not a model-forward-only measurement. See each package for stage/load times and runtime for the complete inspection. Torch allocation excludes other applications and driver allocations.
Whole-process latency reflects variable host load; the table does not establish a controlled end-to-end speedup. CPU/CUDA kernel timings below compare repeated operations within one process under matched conditions.

## Per-category results on the 17 current pairs

| Category | Frozen v3 | v3.1 |
|---|---|---|
| bag | {'inconclusive': 4} | {'inconclusive': 4} |
| clock | {'comparable': 2, 'inconclusive': 1} | {'comparable': 2, 'inconclusive': 1} |
| phone | {'inconclusive': 3} | {'comparable': 1, 'inconclusive': 2} |
| shoes | {'comparable': 1, 'inconclusive': 2, 'failed': 1} | {'inconclusive': 3, 'comparable': 1} |
| speaker | {'comparable': 3} | {'comparable': 3} |

## Other evaluation groups

```json
{
  "baseline": {
    "real_pair": {
      "count": 17,
      "outcomes": {
        "inconclusive": 10,
        "comparable": 6,
        "failed": 1
      },
      "proposal_jobs": 5,
      "boundary_jobs": 1,
      "confirmed_identity_jobs": 0,
      "median_wall_seconds": 21.913549799995963,
      "peak_cuda_allocated_bytes": 501436416,
      "peak_cuda_reserved_bytes": 698351616,
      "peak_host_bytes": 1760808960,
      "categories": {
        "bag": {
          "inconclusive": 4
        },
        "clock": {
          "comparable": 2,
          "inconclusive": 1
        },
        "phone": {
          "inconclusive": 3
        },
        "shoes": {
          "comparable": 1,
          "inconclusive": 2,
          "failed": 1
        },
        "speaker": {
          "comparable": 3
        }
      }
    },
    "multiview": {
      "count": 5,
      "outcomes": {
        "inconclusive": 2,
        "partially_comparable": 1,
        "failed": 1,
        "comparable": 1
      },
      "proposal_jobs": 2,
      "boundary_jobs": 1,
      "confirmed_identity_jobs": 0,
      "median_wall_seconds": 27.236362999996345,
      "peak_cuda_allocated_bytes": 501436416,
      "peak_cuda_reserved_bytes": 903872512,
      "peak_host_bytes": 1782538240,
      "categories": {
        "bag": {
          "inconclusive": 1
        },
        "clock": {
          "partially_comparable": 1
        },
        "phone": {
          "inconclusive": 1
        },
        "shoes": {
          "failed": 1
        },
        "speaker": {
          "comparable": 1
        }
      }
    },
    "exact_repeat_control": {
      "count": 17,
      "outcomes": {
        "comparable": 14,
        "failed": 3
      },
      "proposal_jobs": 0,
      "boundary_jobs": 0,
      "confirmed_identity_jobs": 0,
      "median_wall_seconds": 17.532046399996034,
      "peak_cuda_allocated_bytes": 501436416,
      "peak_cuda_reserved_bytes": 698351616,
      "peak_host_bytes": 1764687872,
      "categories": {
        "bag": {
          "comparable": 4
        },
        "clock": {
          "comparable": 3
        },
        "phone": {
          "failed": 1,
          "comparable": 2
        },
        "shoes": {
          "failed": 1,
          "comparable": 3
        },
        "speaker": {
          "comparable": 2,
          "failed": 1
        }
      }
    },
    "different_object_control": {
      "count": 5,
      "outcomes": {
        "inconclusive": 5
      },
      "proposal_jobs": 0,
      "boundary_jobs": 0,
      "confirmed_identity_jobs": 0,
      "median_wall_seconds": 11.910086600000795,
      "peak_cuda_allocated_bytes": 486303744,
      "peak_cuda_reserved_bytes": 698351616,
      "peak_host_bytes": 1472909312,
      "categories": {
        "bag/clock": {
          "inconclusive": 1
        },
        "clock/phone": {
          "inconclusive": 1
        },
        "phone/shoes": {
          "inconclusive": 1
        },
        "shoes/speaker": {
          "inconclusive": 1
        },
        "speaker/bag": {
          "inconclusive": 1
        }
      }
    },
    "historical_unlabeled_pair": {
      "count": 12,
      "outcomes": {
        "failed": 5,
        "comparable": 7
      },
      "proposal_jobs": 3,
      "boundary_jobs": 1,
      "confirmed_identity_jobs": 0,
      "median_wall_seconds": 11.544227449998289,
      "peak_cuda_allocated_bytes": 501436416,
      "peak_cuda_reserved_bytes": 698351616,
      "peak_host_bytes": 1766494208,
      "categories": {
        "bag": {
          "failed": 1,
          "comparable": 2
        },
        "clock": {
          "failed": 1,
          "comparable": 2
        },
        "phone": {
          "failed": 1,
          "comparable": 2
        },
        "speaker": {
          "failed": 2,
          "comparable": 1
        }
      }
    }
  },
  "current": {
    "real_pair": {
      "count": 17,
      "outcomes": {
        "inconclusive": 10,
        "comparable": 7
      },
      "proposal_jobs": 6,
      "boundary_jobs": 1,
      "confirmed_identity_jobs": 0,
      "median_wall_seconds": 12.627573099998699,
      "peak_cuda_allocated_bytes": 501436416,
      "peak_cuda_reserved_bytes": 698351616,
      "peak_host_bytes": 1781047296,
      "categories": {
        "bag": {
          "inconclusive": 4
        },
        "clock": {
          "comparable": 2,
          "inconclusive": 1
        },
        "phone": {
          "comparable": 1,
          "inconclusive": 2
        },
        "shoes": {
          "inconclusive": 3,
          "comparable": 1
        },
        "speaker": {
          "comparable": 3
        }
      }
    },
    "multiview": {
      "count": 5,
      "outcomes": {
        "inconclusive": 1,
        "partially_comparable": 3,
        "comparable": 1
      },
      "proposal_jobs": 4,
      "boundary_jobs": 1,
      "confirmed_identity_jobs": 0,
      "median_wall_seconds": 12.32802040000388,
      "peak_cuda_allocated_bytes": 501436416,
      "peak_cuda_reserved_bytes": 903872512,
      "peak_host_bytes": 1809948672,
      "categories": {
        "bag": {
          "inconclusive": 1
        },
        "clock": {
          "partially_comparable": 1
        },
        "phone": {
          "partially_comparable": 1
        },
        "shoes": {
          "partially_comparable": 1
        },
        "speaker": {
          "comparable": 1
        }
      }
    },
    "exact_repeat_control": {
      "count": 17,
      "outcomes": {
        "comparable": 17
      },
      "proposal_jobs": 0,
      "boundary_jobs": 0,
      "confirmed_identity_jobs": 0,
      "median_wall_seconds": 7.91147269999783,
      "peak_cuda_allocated_bytes": 501436416,
      "peak_cuda_reserved_bytes": 698351616,
      "peak_host_bytes": 1772847104,
      "categories": {
        "bag": {
          "comparable": 4
        },
        "clock": {
          "comparable": 3
        },
        "phone": {
          "comparable": 3
        },
        "shoes": {
          "comparable": 4
        },
        "speaker": {
          "comparable": 3
        }
      }
    },
    "different_object_control": {
      "count": 5,
      "outcomes": {
        "inconclusive": 5
      },
      "proposal_jobs": 0,
      "boundary_jobs": 0,
      "confirmed_identity_jobs": 0,
      "median_wall_seconds": 7.08711680000124,
      "peak_cuda_allocated_bytes": 486303744,
      "peak_cuda_reserved_bytes": 698351616,
      "peak_host_bytes": 1499930624,
      "categories": {
        "bag/clock": {
          "inconclusive": 1
        },
        "clock/phone": {
          "inconclusive": 1
        },
        "phone/shoes": {
          "inconclusive": 1
        },
        "shoes/speaker": {
          "inconclusive": 1
        },
        "speaker/bag": {
          "inconclusive": 1
        }
      }
    },
    "historical_unlabeled_pair": {
      "count": 12,
      "outcomes": {
        "comparable": 11,
        "inconclusive": 1
      },
      "proposal_jobs": 2,
      "boundary_jobs": 1,
      "confirmed_identity_jobs": 0,
      "median_wall_seconds": 7.896020499996666,
      "peak_cuda_allocated_bytes": 487680000,
      "peak_cuda_reserved_bytes": 698351616,
      "peak_host_bytes": 1630855168,
      "categories": {
        "bag": {
          "comparable": 3
        },
        "clock": {
          "comparable": 2,
          "inconclusive": 1
        },
        "phone": {
          "comparable": 3
        },
        "speaker": {
          "comparable": 3
        }
      }
    }
  }
}
```

## Regression execution

```json
{
  "all-final.xml": {
    "tests": 278.0,
    "failures": 0.0,
    "errors": 1.0,
    "skipped": 17.0,
    "time": 168.459
  },
  "all-tests.xml": {
    "tests": 277.0,
    "failures": 0.0,
    "errors": 1.0,
    "skipped": 17.0,
    "time": 139.479
  },
  "complete-software-tests.xml": {
    "tests": 280.0,
    "failures": 0.0,
    "errors": 0.0,
    "skipped": 17.0,
    "time": 66.636
  },
  "first-tests.xml": {
    "tests": 20.0,
    "failures": 1.0,
    "errors": 0.0,
    "skipped": 0.0,
    "time": 14.574
  },
  "policy-final.xml": {
    "tests": 2.0,
    "failures": 0.0,
    "errors": 0.0,
    "skipped": 0.0,
    "time": 0.19
  },
  "release-all-tests.xml": {
    "tests": 285.0,
    "failures": 0.0,
    "errors": 0.0,
    "skipped": 2.0,
    "time": 181.826
  },
  "rename-recheck.xml": {
    "tests": 1.0,
    "failures": 0.0,
    "errors": 0.0,
    "skipped": 0.0,
    "time": 3.221
  },
  "rotation-regression.xml": {
    "tests": 22.0,
    "failures": 0.0,
    "errors": 0.0,
    "skipped": 0.0,
    "time": 3.65
  },
  "storage-fixed.xml": {
    "tests": 29.0,
    "failures": 0.0,
    "errors": 0.0,
    "skipped": 0.0,
    "time": 45.218
  },
  "targeted-final.xml": {
    "tests": 20.0,
    "failures": 0.0,
    "errors": 0.0,
    "skipped": 0.0,
    "time": 6.731
  },
  "targeted-tests.xml": {
    "tests": 36.0,
    "failures": 3.0,
    "errors": 0.0,
    "skipped": 0.0,
    "time": 16.602
  }
}
```

Earlier failed test executions remain in the ledger. Windows directory-rename failures were reproduced and fixed with a verified transactional copy fallback; final results must be read from the final complete suite, not an isolated retry.

## Integrity and limitations

Validated 56 current packages and 1746 artifact digests across both revisions. Matched evaluation complete: {'baseline': True, 'current': True}. Changed safety thresholds: [].

The same frozen targets, derivatives, model hashes, seeds and configuration were used. The initial run without EP-local Kornia is retained separately under `baseline/`; it is a dependency diagnostic and is excluded from this comparison.
The later `current-complete` and `current-final` partial campaigns are preserved development measurements; only `current-release` is the final reviewed implementation.

All returned outputs are advisory, with payment_action=none and physical identity unverified. The different-object confirmation gate is passed through abstention; positive physical-identity recognition accuracy is not established. All accepted alignments pass internal verification; registration ground-truth accuracy is NOT VERIFIED.

Integration readiness: the stable local API and private reports are available for human inspection. No NeighborLend integration was performed. A physical-damage pilot requires independently reviewed unchanged/damaged recaptures, instance/region labels, distinctive identity evidence and an object-level held-out evaluation. Larger configured 12-image/64-megapixel combinations have not been stress-verified by this dataset.

Archived photographs form a separate unlabeled regression group. Some archived named before/after images are byte-identical. No independently labeled physical damage, unchanged recaptures, region labels, or independent physical-object holdout exists. Different-object controls are different categories; similar-looking different instances remain unverified. Software controls do not replace these missing labels.

No cross-view surface map, automatic physical identity confirmation, damage promotion, or exhaustive original-resolution scratch search is claimed. Review crops retain original detail only around proposed regions. Hidden/touching instances remain unresolved.

[Architecture, contract, limits and reproduction](ep-v31.md). [Private visual gallery](../.test-artifacts/ep-v31-20261111/index.html). [Acceptance evidence](../.test-artifacts/ep-v31-20261111/acceptance.json).

## CPU/CUDA kernel measurements

```json
{
  "alignment": {
    "opencv": {
      "median_seconds": 0.022454199999629054,
      "samples_seconds": [
        0.02393570000276668,
        0.02254390000598505,
        0.025642100001277868,
        0.022454199999629054,
        0.021719099997426383,
        0.02151869999943301,
        0.021992599999066442
      ]
    },
    "cuda": {
      "median_seconds": 0.031098999999812804,
      "samples_seconds": [
        0.03278160000627395,
        0.03495470000052592,
        0.031098999999812804,
        0.027736199997889344,
        0.027242999996815342,
        0.029046100004052278,
        0.03211580000061076
      ]
    },
    "mean_absolute_pixel_error": 0.004075311312328746,
    "overlap_iou": 1.0
  },
  "appearance": {
    "opencv": {
      "median_seconds": 0.11291129999881377,
      "samples_seconds": [
        0.12751250000292202,
        0.12327060000097845,
        0.11291129999881377,
        0.1134029000022565,
        0.11175850000290666,
        0.09365889999753563,
        0.1067962000015541
      ]
    },
    "cuda": {
      "median_seconds": 0.024503100001311395,
      "samples_seconds": [
        0.024503100001311395,
        0.02538990000175545,
        0.02517249999800697,
        0.024425900002825074,
        0.024218099999416154,
        0.023342999993474223,
        0.02495229999476578
      ]
    },
    "max_map_error": 1.1920928955078125e-06,
    "cpu_regions": [
      [
        249,
        199,
        33,
        253,
        755,
        0.42598849534988403
      ]
    ],
    "gpu_regions": [
      [
        249,
        199,
        33,
        253,
        755,
        0.42598843574523926
      ]
    ]
  },
  "rootsift_feature_extraction": {
    "median_seconds": 0.7881140999961644,
    "samples_seconds": [
      0.7239850999976625,
      0.7281655999977374,
      0.7881140999961644,
      0.8247558000002755,
      0.8109710999997333
    ]
  },
  "geometry": {
    "opencv": {
      "median_seconds": 0.009109600003284868,
      "samples_seconds": [
        0.008801299998594914,
        0.00787980000313837,
        0.009022800004458986,
        0.009109600003284868,
        0.010192699999606702,
        0.012601000002177898,
        0.01131100000202423
      ]
    },
    "kornia_cuda": {
      "median_seconds": 0.1018608000013046,
      "samples_seconds": [
        0.09595020000415388,
        0.09108719999494497,
        0.09457810000458267,
        0.11222039999847766,
        0.10583060000499245,
        0.10424679999414366,
        0.1018608000013046
      ]
    },
    "cpu_support": {
      "inliers": 276,
      "inlier_ratio": 1.0,
      "median_reprojection_error": 0.08831346035003662,
      "symmetric_reprojection_error": 0.08917715400457382,
      "source_coverage": 0.9522736326050525,
      "target_coverage": 0.9528562474892632,
      "geometry_model": "homography"
    },
    "gpu_support": {
      "inliers": 276,
      "inlier_ratio": 1.0,
      "median_reprojection_error": 0.15710245072841644,
      "symmetric_reprojection_error": 0.15803010761737823,
      "source_coverage": 0.9522736326050525,
      "target_coverage": 0.9528562474892632,
      "geometry_model": "homography"
    }
  },
  "matching_cold": [
    {
      "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
      "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
      "selected": "dinov2_rootsift_bidirectional_v3",
      "attempts": [
        {
          "matcher": "rootsift",
          "seconds": 0.11780690000159666,
          "valid": true,
          "resources": {
            "process_rss_bytes": 1502715904,
            "process_peak_working_set_bytes": 1502715904,
            "current_cuda_allocated_bytes": 8519680,
            "cuda_high_water_bytes": 54620672
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_rootsift_bidirectional_v3",
          "cosine_similarity": 0.99,
          "matches": 218,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 218,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.08645354211330414,
          "overlap_fraction": 0.0,
          "homography": [
            [
              0.9999455465771881,
              0.009980400889973188,
              3.0090808941381497
            ],
            [
              0.007982848723254108,
              0.9999360977655394,
              -1.986538600228637
            ],
            [
              9.913379168735556e-06,
              -3.307200630221131e-09,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9495407664318589,
          "target_coverage": 0.9499548197450146,
          "symmetric_reprojection_error": 0.0869152769446373
        },
        {
          "matcher": "loftr",
          "seconds": 1.994026100001065,
          "valid": true,
          "model_load_seconds": 0.857912600004056,
          "resources": {
            "process_rss_bytes": 1773772800,
            "process_peak_working_set_bytes": 1796792320,
            "current_cuda_allocated_bytes": 123359232,
            "cuda_high_water_bytes": 944249344
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_loftr_verified_v3",
          "cosine_similarity": 0.99,
          "matches": 3024,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 3024,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.46440473198890686,
          "overlap_fraction": 0.0,
          "homography": [
            [
              1.0012442222344013,
              0.010227734610685347,
              2.6199535270675676
            ],
            [
              0.008419412764163709,
              1.000638730575883,
              -2.1672271158427354
            ],
            [
              1.0949893409078803e-05,
              4.932056063646702e-07,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9663889686871588,
          "target_coverage": 0.9708118966131541,
          "symmetric_reprojection_error": 0.4661678671836853
        }
      ]
    }
  ],
  "matching": [
    {
      "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
      "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
      "selected": "dinov2_rootsift_bidirectional_v3",
      "attempts": [
        {
          "matcher": "rootsift",
          "seconds": 0.11517860000458313,
          "valid": true,
          "resources": {
            "process_rss_bytes": 1774047232,
            "process_peak_working_set_bytes": 1796792320,
            "current_cuda_allocated_bytes": 123359232,
            "cuda_high_water_bytes": 945297920
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_rootsift_bidirectional_v3",
          "cosine_similarity": 0.99,
          "matches": 218,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 218,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.08645354211330414,
          "overlap_fraction": 0.0,
          "homography": [
            [
              0.9999455465771881,
              0.009980400889973188,
              3.0090808941381497
            ],
            [
              0.007982848723254108,
              0.9999360977655394,
              -1.986538600228637
            ],
            [
              9.913379168735556e-06,
              -3.307200630221131e-09,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9495407664318589,
          "target_coverage": 0.9499548197450146,
          "symmetric_reprojection_error": 0.0869152769446373
        },
        {
          "matcher": "loftr",
          "seconds": 0.48760980000224663,
          "valid": true,
          "model_load_seconds": 0.857912600004056,
          "resources": {
            "process_rss_bytes": 1774051328,
            "process_peak_working_set_bytes": 1796792320,
            "current_cuda_allocated_bytes": 123359232,
            "cuda_high_water_bytes": 945297920
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_loftr_verified_v3",
          "cosine_similarity": 0.99,
          "matches": 3024,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 3024,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.46440473198890686,
          "overlap_fraction": 0.0,
          "homography": [
            [
              1.0012442222344013,
              0.010227734610685347,
              2.6199535270675676
            ],
            [
              0.008419412764163709,
              1.000638730575883,
              -2.1672271158427354
            ],
            [
              1.0949893409078803e-05,
              4.932056063646702e-07,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9663889686871588,
          "target_coverage": 0.9708118966131541,
          "symmetric_reprojection_error": 0.4661678671836853
        }
      ]
    },
    {
      "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
      "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
      "selected": "dinov2_rootsift_bidirectional_v3",
      "attempts": [
        {
          "matcher": "rootsift",
          "seconds": 0.09871150000253692,
          "valid": true,
          "resources": {
            "process_rss_bytes": 1774051328,
            "process_peak_working_set_bytes": 1796792320,
            "current_cuda_allocated_bytes": 123359232,
            "cuda_high_water_bytes": 945297920
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_rootsift_bidirectional_v3",
          "cosine_similarity": 0.99,
          "matches": 218,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 218,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.08645354211330414,
          "overlap_fraction": 0.0,
          "homography": [
            [
              0.9999455465771881,
              0.009980400889973188,
              3.0090808941381497
            ],
            [
              0.007982848723254108,
              0.9999360977655394,
              -1.986538600228637
            ],
            [
              9.913379168735556e-06,
              -3.307200630221131e-09,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9495407664318589,
          "target_coverage": 0.9499548197450146,
          "symmetric_reprojection_error": 0.0869152769446373
        },
        {
          "matcher": "loftr",
          "seconds": 0.4333307999986573,
          "valid": true,
          "model_load_seconds": 0.857912600004056,
          "resources": {
            "process_rss_bytes": 1774067712,
            "process_peak_working_set_bytes": 1796792320,
            "current_cuda_allocated_bytes": 123359232,
            "cuda_high_water_bytes": 945297920
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_loftr_verified_v3",
          "cosine_similarity": 0.99,
          "matches": 3024,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 3024,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.46440473198890686,
          "overlap_fraction": 0.0,
          "homography": [
            [
              1.0012442222344013,
              0.010227734610685347,
              2.6199535270675676
            ],
            [
              0.008419412764163709,
              1.000638730575883,
              -2.1672271158427354
            ],
            [
              1.0949893409078803e-05,
              4.932056063646702e-07,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9663889686871588,
          "target_coverage": 0.9708118966131541,
          "symmetric_reprojection_error": 0.4661678671836853
        }
      ]
    },
    {
      "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
      "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
      "selected": "dinov2_rootsift_bidirectional_v3",
      "attempts": [
        {
          "matcher": "rootsift",
          "seconds": 0.10884500000247499,
          "valid": true,
          "resources": {
            "process_rss_bytes": 1774067712,
            "process_peak_working_set_bytes": 1796792320,
            "current_cuda_allocated_bytes": 123359232,
            "cuda_high_water_bytes": 945297920
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_rootsift_bidirectional_v3",
          "cosine_similarity": 0.99,
          "matches": 218,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 218,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.08645354211330414,
          "overlap_fraction": 0.0,
          "homography": [
            [
              0.9999455465771881,
              0.009980400889973188,
              3.0090808941381497
            ],
            [
              0.007982848723254108,
              0.9999360977655394,
              -1.986538600228637
            ],
            [
              9.913379168735556e-06,
              -3.307200630221131e-09,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9495407664318589,
          "target_coverage": 0.9499548197450146,
          "symmetric_reprojection_error": 0.0869152769446373
        },
        {
          "matcher": "loftr",
          "seconds": 0.4297404999961145,
          "valid": true,
          "model_load_seconds": 0.857912600004056,
          "resources": {
            "process_rss_bytes": 1774075904,
            "process_peak_working_set_bytes": 1796792320,
            "current_cuda_allocated_bytes": 123359232,
            "cuda_high_water_bytes": 945297920
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_loftr_verified_v3",
          "cosine_similarity": 0.99,
          "matches": 3024,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 3024,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.46440473198890686,
          "overlap_fraction": 0.0,
          "homography": [
            [
              1.0012442222344013,
              0.010227734610685347,
              2.6199535270675676
            ],
            [
              0.008419412764163709,
              1.000638730575883,
              -2.1672271158427354
            ],
            [
              1.0949893409078803e-05,
              4.932056063646702e-07,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9663889686871588,
          "target_coverage": 0.9708118966131541,
          "symmetric_reprojection_error": 0.4661678671836853
        }
      ]
    },
    {
      "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
      "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
      "selected": "dinov2_rootsift_bidirectional_v3",
      "attempts": [
        {
          "matcher": "rootsift",
          "seconds": 0.1321609000005992,
          "valid": true,
          "resources": {
            "process_rss_bytes": 1774075904,
            "process_peak_working_set_bytes": 1796792320,
            "current_cuda_allocated_bytes": 123359232,
            "cuda_high_water_bytes": 945297920
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_rootsift_bidirectional_v3",
          "cosine_similarity": 0.99,
          "matches": 218,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 218,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.08645354211330414,
          "overlap_fraction": 0.0,
          "homography": [
            [
              0.9999455465771881,
              0.009980400889973188,
              3.0090808941381497
            ],
            [
              0.007982848723254108,
              0.9999360977655394,
              -1.986538600228637
            ],
            [
              9.913379168735556e-06,
              -3.307200630221131e-09,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9495407664318589,
          "target_coverage": 0.9499548197450146,
          "symmetric_reprojection_error": 0.0869152769446373
        },
        {
          "matcher": "loftr",
          "seconds": 0.42042829999991227,
          "valid": true,
          "model_load_seconds": 0.857912600004056,
          "resources": {
            "process_rss_bytes": 1774075904,
            "process_peak_working_set_bytes": 1796792320,
            "current_cuda_allocated_bytes": 123359232,
            "cuda_high_water_bytes": 945297920
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_loftr_verified_v3",
          "cosine_similarity": 0.99,
          "matches": 3024,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 3024,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.46440473198890686,
          "overlap_fraction": 0.0,
          "homography": [
            [
              1.0012442222344013,
              0.010227734610685347,
              2.6199535270675676
            ],
            [
              0.008419412764163709,
              1.000638730575883,
              -2.1672271158427354
            ],
            [
              1.0949893409078803e-05,
              4.932056063646702e-07,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9663889686871588,
          "target_coverage": 0.9708118966131541,
          "symmetric_reprojection_error": 0.4661678671836853
        }
      ]
    },
    {
      "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
      "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
      "selected": "dinov2_rootsift_bidirectional_v3",
      "attempts": [
        {
          "matcher": "rootsift",
          "seconds": 0.13495939999847906,
          "valid": true,
          "resources": {
            "process_rss_bytes": 1774075904,
            "process_peak_working_set_bytes": 1796792320,
            "current_cuda_allocated_bytes": 123359232,
            "cuda_high_water_bytes": 945297920
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_rootsift_bidirectional_v3",
          "cosine_similarity": 0.99,
          "matches": 218,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 218,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.08645354211330414,
          "overlap_fraction": 0.0,
          "homography": [
            [
              0.9999455465771881,
              0.009980400889973188,
              3.0090808941381497
            ],
            [
              0.007982848723254108,
              0.9999360977655394,
              -1.986538600228637
            ],
            [
              9.913379168735556e-06,
              -3.307200630221131e-09,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9495407664318589,
          "target_coverage": 0.9499548197450146,
          "symmetric_reprojection_error": 0.0869152769446373
        },
        {
          "matcher": "loftr",
          "seconds": 0.41323990000091726,
          "valid": true,
          "model_load_seconds": 0.857912600004056,
          "resources": {
            "process_rss_bytes": 1774080000,
            "process_peak_working_set_bytes": 1796792320,
            "current_cuda_allocated_bytes": 123359232,
            "cuda_high_water_bytes": 945297920
          },
          "schema_version": "2.0",
          "before_id": "ad3da19e-5928-4766-bea9-616341849e06",
          "after_id": "137f2e7e-6099-4a57-9e20-072780ca2a79",
          "status": "inconclusive",
          "identity": "consistent_visual_evidence",
          "method": "dinov2_loftr_verified_v3",
          "cosine_similarity": 0.99,
          "matches": 3024,
          "local_matching_evaluated": true,
          "alignment_status": "not_attempted",
          "overlap_id": null,
          "inliers": 3024,
          "inlier_ratio": 1.0,
          "median_reprojection_error": 0.46440473198890686,
          "overlap_fraction": 0.0,
          "homography": [
            [
              1.0012442222344013,
              0.010227734610685347,
              2.6199535270675676
            ],
            [
              0.008419412764163709,
              1.000638730575883,
              -2.1672271158427354
            ],
            [
              1.0949893409078803e-05,
              4.932056063646702e-07,
              1.0
            ]
          ],
          "reasons": [],
          "geometry_model": "homography",
          "source_coverage": 0.9663889686871588,
          "target_coverage": 0.9708118966131541,
          "symmetric_reprojection_error": 0.4661678671836853
        }
      ]
    }
  ],
  "matching_warm_median_seconds": {
    "rootsift": 0.11517860000458313,
    "loftr": 0.4297404999961145
  },
  "peak_cuda_allocated_bytes": 945297920,
  "peak_cuda_reserved_bytes": 1340080128
}
```

## Cold-model and warm-cache lifecycle

```json
{
  "baseline": {
    "case": "speaker-back",
    "revision": "baseline",
    "records": [
      {
        "index": 0,
        "kind": "cold_models",
        "seconds": 3.5781881000002613,
        "outcome": "comparable",
        "metrics": {
          "device": "cuda",
          "model_load_seconds": {
            "segment": 0.4755042000033427,
            "embedding": 0.7594796999983373
          },
          "model_weight_sha256": {
            "segment": "dff858b19600a46461cbb7de98f796b23a7a888d9f5e34c0b033f7d6eb9e4e6a",
            "embedding": "b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9"
          },
          "neural_forward_seconds": {
            "segment": 0.6856218999892008,
            "embedding": 0.09550929999386426
          },
          "neural_forward_calls": {
            "segment": 2,
            "embedding": 8
          },
          "process_rss_bytes": 1596432384,
          "process_peak_working_set_bytes": 1599799296,
          "peak_cuda_allocated_bytes": 486303744,
          "peak_cuda_reserved_bytes": 698351616,
          "available_ram_bytes": 5155758080,
          "requested_device": "cuda",
          "embedding_cache_hits": 0,
          "embedding_cache_entries": 2
        }
      },
      {
        "index": 1,
        "kind": "warm_embedding_cache",
        "seconds": 2.1806065999990096,
        "outcome": "comparable",
        "metrics": {
          "device": "cuda",
          "model_load_seconds": {
            "segment": 0.5866747000036412,
            "embedding": 0.7594796999983373
          },
          "model_weight_sha256": {
            "segment": "dff858b19600a46461cbb7de98f796b23a7a888d9f5e34c0b033f7d6eb9e4e6a",
            "embedding": "b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9"
          },
          "neural_forward_seconds": {
            "segment": 0.8900615999882575,
            "embedding": 0.09550929999386426
          },
          "neural_forward_calls": {
            "segment": 4,
            "embedding": 8
          },
          "process_rss_bytes": 1572253696,
          "process_peak_working_set_bytes": 1684717568,
          "peak_cuda_allocated_bytes": 486303744,
          "peak_cuda_reserved_bytes": 698351616,
          "available_ram_bytes": 5155758080,
          "requested_device": "cuda",
          "embedding_cache_hits": 2,
          "embedding_cache_entries": 2
        }
      },
      {
        "index": 2,
        "kind": "warm_embedding_cache",
        "seconds": 2.098116099994513,
        "outcome": "comparable",
        "metrics": {
          "device": "cuda",
          "model_load_seconds": {
            "segment": 0.46960499999840977,
            "embedding": 0.7594796999983373
          },
          "model_weight_sha256": {
            "segment": "dff858b19600a46461cbb7de98f796b23a7a888d9f5e34c0b033f7d6eb9e4e6a",
            "embedding": "b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9"
          },
          "neural_forward_seconds": {
            "segment": 1.0893887999845902,
            "embedding": 0.09550929999386426
          },
          "neural_forward_calls": {
            "segment": 6,
            "embedding": 8
          },
          "process_rss_bytes": 1578876928,
          "process_peak_working_set_bytes": 1684717568,
          "peak_cuda_allocated_bytes": 486303744,
          "peak_cuda_reserved_bytes": 698351616,
          "available_ram_bytes": 5155758080,
          "requested_device": "cuda",
          "embedding_cache_hits": 4,
          "embedding_cache_entries": 2
        }
      }
    ],
    "scope": "Same in-memory pixels; imports/decoder excluded; original-detail crops disabled equally",
    "policy": "Models released per inspection; bounded CPU embedding LRU persists across calls"
  },
  "current": {
    "case": "speaker-back",
    "revision": "current",
    "records": [
      {
        "index": 0,
        "kind": "cold_models",
        "seconds": 3.453355700003158,
        "outcome": "comparable",
        "metrics": {
          "device": "cuda",
          "model_load_seconds": {
            "segment": 0.49996099999407306,
            "embedding": 0.7452359999952023
          },
          "model_weight_sha256": {
            "segment": "dff858b19600a46461cbb7de98f796b23a7a888d9f5e34c0b033f7d6eb9e4e6a",
            "embedding": "b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9"
          },
          "neural_forward_seconds": {
            "segment": 0.5899549999958253,
            "embedding": 0.07150270000420278
          },
          "neural_forward_calls": {
            "segment": 2,
            "embedding": 8
          },
          "process_rss_bytes": 1570545664,
          "process_peak_working_set_bytes": 1596362752,
          "peak_cuda_allocated_bytes": 486303744,
          "peak_cuda_reserved_bytes": 698351616,
          "available_ram_bytes": 5166800896,
          "requested_device": "cuda",
          "embedding_cache_hits": 0,
          "embedding_cache_entries": 2
        }
      },
      {
        "index": 1,
        "kind": "warm_embedding_cache",
        "seconds": 2.0245891000013216,
        "outcome": "comparable",
        "metrics": {
          "device": "cuda",
          "model_load_seconds": {
            "segment": 0.4554476999983308,
            "embedding": 0.7452359999952023
          },
          "model_weight_sha256": {
            "segment": "dff858b19600a46461cbb7de98f796b23a7a888d9f5e34c0b033f7d6eb9e4e6a",
            "embedding": "b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9"
          },
          "neural_forward_seconds": {
            "segment": 0.7880015999980969,
            "embedding": 0.07150270000420278
          },
          "neural_forward_calls": {
            "segment": 4,
            "embedding": 8
          },
          "process_rss_bytes": 1587417088,
          "process_peak_working_set_bytes": 1660715008,
          "peak_cuda_allocated_bytes": 486303744,
          "peak_cuda_reserved_bytes": 698351616,
          "available_ram_bytes": 5166800896,
          "requested_device": "cuda",
          "embedding_cache_hits": 2,
          "embedding_cache_entries": 2
        }
      },
      {
        "index": 2,
        "kind": "warm_embedding_cache",
        "seconds": 1.994416599998658,
        "outcome": "comparable",
        "metrics": {
          "device": "cuda",
          "model_load_seconds": {
            "segment": 0.41618469999957597,
            "embedding": 0.7452359999952023
          },
          "model_weight_sha256": {
            "segment": "dff858b19600a46461cbb7de98f796b23a7a888d9f5e34c0b033f7d6eb9e4e6a",
            "embedding": "b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9"
          },
          "neural_forward_seconds": {
            "segment": 0.9842807999957586,
            "embedding": 0.07150270000420278
          },
          "neural_forward_calls": {
            "segment": 6,
            "embedding": 8
          },
          "process_rss_bytes": 1585926144,
          "process_peak_working_set_bytes": 1660715008,
          "peak_cuda_allocated_bytes": 486303744,
          "peak_cuda_reserved_bytes": 698351616,
          "available_ram_bytes": 5166800896,
          "requested_device": "cuda",
          "embedding_cache_hits": 4,
          "embedding_cache_entries": 2
        }
      }
    ],
    "scope": "Same in-memory pixels; imports/decoder excluded; original-detail crops disabled equally",
    "policy": "Models released per inspection; bounded CPU embedding LRU persists across calls"
  }
}
```

## Files changed from the frozen source

- `README.md`
- `docs/ep-v31-failure.schema.json`
- `docs/ep-v31-release-report.md`
- `docs/ep-v31-report.schema.json`
- `docs/ep-v31-request.schema.json`
- `docs/ep-v31.md`
- `ep_engine/cv/contracts.py`
- `ep_engine/cv/geometry.py`
- `ep_engine/cv/numerics.py`
- `ep_engine/cv/pipeline.py`
- `ep_engine/cv/store.py`
- `ep_engine/cv/worker.py`
- `ep_engine/v3/matching.py`
- `ep_engine/v3/pipeline.py`
- `ep_engine/v31/__init__.py`
- `ep_engine/v31/api.py`
- `ep_engine/v31/contracts.py`
- `ep_engine/v31/pipeline.py`
- `ep_engine/v31/worker.py`
- `scripts/audit_v31.py`
- `scripts/benchmark_v31_lifecycle.py`
- `scripts/evaluate_v31.py`
- `scripts/probe_v31_instances.py`
- `scripts/probe_v31_matching.py`
- `scripts/report_v31.py`
- `scripts/run_v31.py`
- `tests/integration/test_cv_service.py`
- `tests/integration/test_v31_native.py`
- `tests/regression/test_v31.py`
- `tests/unit/test_v3.py`
