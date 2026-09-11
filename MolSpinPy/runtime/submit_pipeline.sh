#!/bin/bash
# Usage: submit_pipeline.sh <workspace_directory>
WORKSPACE_DIR="${1:-.}"

ARRAY_JOB_ID=$(sbatch --parsable "$WORKSPACE_DIR/job_script.sh")
EPILOGUE_JOB_ID=$(sbatch --parsable \
       --dependency=afterok:$ARRAY_JOB_ID \
       --export=ALL,SLURM_ARRAY_JOB_ID=$ARRAY_JOB_ID \
       "$WORKSPACE_DIR/epilogue_script.sh")
echo "SUBMITTED:$ARRAY_JOB_ID,$EPILOGUE_JOB_ID"
