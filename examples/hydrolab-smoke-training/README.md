# HydroLab smoke training project

Import this directory from **模型代码 / 模板 → 服务器目录**, then create the template with:

```text
python main.py --epochs 1 --experiment {experiment} --output-dir {OUTPUT_DIR}
```

The script also reads `HYDROLAB_OUTPUT_DIR`, so either integration style uses
the same writable output root. All metrics, predictions, plots, checkpoints,
and configuration files are created under
`$HYDROLAB_OUTPUT_DIR/experiments/<experiment>/`; it never writes into the
imported code directory.
