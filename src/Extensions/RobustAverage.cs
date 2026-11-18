using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Reactive.Linq;
using Bonsai;
using OpenCV.Net;
using OpenTK;

namespace UclOpenFreeingVisionBenchmark
{
    /// <summary>
    /// Specifies how a batch of 3D samples is reduced to a single point.
    /// </summary>
    public enum RobustAverageMethod
    {
        /// <summary>Arithmetic mean of the inlier samples.</summary>
        Mean,
        /// <summary>Per-axis median of the inlier samples.</summary>
        Median
    }

    /// <summary>
    /// Collects batches of 3D points (e.g. ArUco marker translations from a static camera) and emits a
    /// robust average for each batch, rejecting outliers and invalid samples.
    /// </summary>
    /// <remarks>
    /// Non-finite samples and samples exactly at the origin (which is what a missing detection can produce)
    /// are discarded before they count towards <see cref="Count"/>. Within each batch, a sample is an outlier
    /// if its distance from the per-axis median exceeds median(d) + OutlierThreshold * 1.4826 * MAD(d), where
    /// d are the distances of all samples from the per-axis median.
    /// </remarks>
    [Combinator]
    [Description("Emits a robust (outlier-rejected) average of each batch of 3D points.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class RobustAverage
    {
        int count = 100;
        double outlierThreshold = 3.0;

        [Description("The number of valid samples in each batch.")]
        public int Count
        {
            get { return count; }
            set { count = value; }
        }

        [Description("The number of valid samples to skip between the start of consecutive batches. " +
                     "If not specified, batches do not overlap (Skip = Count). Set to 1 for a sliding window.")]
        public int? Skip { get; set; }

        [Description("How the inlier samples are combined into a single point.")]
        public RobustAverageMethod Method { get; set; }

        [Description("Outlier rejection threshold in robust standard deviations (MAD units). " +
                     "Set to zero or a negative value to disable outlier rejection.")]
        public double OutlierThreshold
        {
            get { return outlierThreshold; }
            set { outlierThreshold = value; }
        }

        public IObservable<Vector3d> Process(IObservable<Vector3d> source)
        {
            return ProcessBatches(source);
        }

        IObservable<Vector3d> ProcessBatches(IObservable<Vector3d> source)
        {
            return Observable.Defer(() =>
            {
                var batchSize = Count;
                var skip = Skip.GetValueOrDefault(batchSize);
                if (batchSize < 1) throw new InvalidOperationException("Count must be at least 1.");
                if (skip < 1) throw new InvalidOperationException("Skip must be at least 1.");

                var method = Method;
                var threshold = OutlierThreshold;
                return source
                    .Where(IsValid)
                    .Buffer(batchSize, skip)
                    .Where(batch => batch.Count == batchSize) // drop the incomplete trailing batches
                    .Select(batch => Average(batch, method, threshold));
            });
        }

        static bool IsValid(Vector3d v)
        {
            var finite = !double.IsNaN(v.X) && !double.IsNaN(v.Y) && !double.IsNaN(v.Z) &&
                         !double.IsInfinity(v.X) && !double.IsInfinity(v.Y) && !double.IsInfinity(v.Z);
            return finite && !(v.X == 0 && v.Y == 0 && v.Z == 0);
        }

        internal static Vector3d Average(IList<Vector3d> samples, RobustAverageMethod method, double threshold)
        {
            var center = new Vector3d(
                Median(samples.Select(v => v.X)),
                Median(samples.Select(v => v.Y)),
                Median(samples.Select(v => v.Z)));

            IList<Vector3d> inliers = samples;
            if (threshold > 0 && samples.Count > 2)
            {
                var distances = samples.Select(v => (v - center).Length).ToArray();
                var medianDistance = Median(distances);
                var mad = Median(distances.Select(d => Math.Abs(d - medianDistance)));
                var limit = medianDistance + threshold * 1.4826 * mad;
                inliers = samples.Where((v, i) => distances[i] <= limit).ToList();
                if (inliers.Count == 0) inliers = samples;
            }

            if (method == RobustAverageMethod.Median)
            {
                return new Vector3d(
                    Median(inliers.Select(v => v.X)),
                    Median(inliers.Select(v => v.Y)),
                    Median(inliers.Select(v => v.Z)));
            }

            var sum = Vector3d.Zero;
            foreach (var v in inliers) sum += v;
            return sum / inliers.Count;
        }

        static double Median(IEnumerable<double> values)
        {
            var sorted = values.OrderBy(x => x).ToArray();
            var mid = sorted.Length / 2;
            return sorted.Length % 2 == 1 ? sorted[mid] : 0.5 * (sorted[mid - 1] + sorted[mid]);
        }
    }
}
