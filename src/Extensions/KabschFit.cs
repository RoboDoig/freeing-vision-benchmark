using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Linq;
using System.Reactive.Linq;
using System.Xml.Serialization;
using Bonsai;
using MathNet.Numerics.LinearAlgebra;
using Newtonsoft.Json.Linq;
using OpenTK;

namespace UclOpenFreeingVisionBenchmark
{
    /// <summary>
    /// The result of a rigid (rotation + translation, no scale) fit between known reference points and
    /// measured points, such that <c>measured ≈ R · reference + t</c>.
    /// </summary>
    public class RigidFit
    {
        /// <summary>
        /// The 3x3 rotation matrix R, row-major (Rotation[row, column]), mapping reference-frame directions
        /// into the measured frame. Its columns are the reference frame's x, y and z axes expressed in the
        /// measured frame.
        /// </summary>
        [XmlIgnore]
        public double[,] Rotation { get; set; }

        /// <summary>The translation t: the reference-frame origin expressed in the measured frame.</summary>
        public Vector3d Translation { get; set; }

        /// <summary>The rotation as a Rodrigues (axis * angle, radians) vector, as used by OpenCV.</summary>
        public Vector3d RotationVector { get; set; }

        /// <summary>
        /// The reference frame's z axis in the measured frame. For a plane whose reference points have z = 0,
        /// this is the plane normal.
        /// </summary>
        public Vector3d Normal { get; set; }

        /// <summary>
        /// The fitted transform as an OpenTK matrix in OpenTK's row-vector convention, i.e.
        /// <c>OpenTK.Vector3.TransformPosition(reference, Transform) ≈ measured</c>. This matches the convention of
        /// Bonsai.Aruco's MarkerViewMatrix and Bonsai.Shaders.
        /// </summary>
        public Matrix4 Transform { get; set; }

        /// <summary>The inverse of <see cref="Transform"/>, mapping measured-frame points into the reference frame.</summary>
        public Matrix4 InverseTransform { get; set; }

        /// <summary>Distance between each measured point and its fitted reference point, in measured units.</summary>
        public double[] Residuals { get; set; }

        /// <summary>Root-mean-square of <see cref="Residuals"/>.</summary>
        public double RmsResidual { get; set; }

        /// <summary>Largest value in <see cref="Residuals"/>.</summary>
        public double MaxResidual { get; set; }

        /// <summary>
        /// The least-squares scale (Umeyama) between the measured and reference point spreads. It is not applied
        /// to the fit. A value far from 1 indicates a mismatch between the marker size given to the detector and
        /// the printed size, or the wrong <c>ReferenceScale</c>.
        /// </summary>
        public double ScaleRatio { get; set; }

        /// <summary>Transforms a reference-frame point into the measured frame using the fit.</summary>
        public Vector3d ToMeasured(Vector3d reference)
        {
            var r = Rotation;
            return new Vector3d(
                r[0, 0] * reference.X + r[0, 1] * reference.Y + r[0, 2] * reference.Z + Translation.X,
                r[1, 0] * reference.X + r[1, 1] * reference.Y + r[1, 2] * reference.Z + Translation.Y,
                r[2, 0] * reference.X + r[2, 1] * reference.Y + r[2, 2] * reference.Z + Translation.Z);
        }

        /// <summary>Transforms a measured-frame point into the reference frame using the inverse of the fit.</summary>
        public Vector3d ToReference(Vector3d measured)
        {
            var r = Rotation;
            var x = measured.X - Translation.X;
            var y = measured.Y - Translation.Y;
            var z = measured.Z - Translation.Z;
            return new Vector3d(
                r[0, 0] * x + r[1, 0] * y + r[2, 0] * z,
                r[0, 1] * x + r[1, 1] * y + r[2, 1] * z,
                r[0, 2] * x + r[1, 2] * y + r[2, 2] * z);
        }

        public override string ToString()
        {
            return string.Format(
                "RigidFit(T=({0:G4}, {1:G4}, {2:G4}), N=({3:F3}, {4:F3}, {5:F3}), Rms={6:G3}, Max={7:G3}, Scale={8:F4})",
                Translation.X, Translation.Y, Translation.Z, Normal.X, Normal.Y, Normal.Z,
                RmsResidual, MaxResidual, ScaleRatio);
        }
    }

    /// <summary>
    /// Finds the rigid transform (Kabsch algorithm: rotation + translation, no scale) that best maps known
    /// reference points onto measured points in the least-squares sense.
    /// </summary>
    /// <remarks>
    /// Intended for arena calibration: the measured points are the averaged 3D marker centres in the camera
    /// frame (e.g. from Bonsai.Aruco), and the reference points are the same markers' known positions in the
    /// arena (plane) frame, so the result is the arena's pose in the camera frame (T_C_P). Measured points must
    /// be given in the same order as the reference points. At least three non-collinear points are required.
    ///
    /// Reference points come from <see cref="ReferenceFileName"/> (the JSON written by
    /// scripts/generate_calibration_sheet.py, selected and ordered by <see cref="MarkerIds"/>) if it is set,
    /// otherwise from <see cref="ReferencePoints"/>. They are multiplied by <see cref="ReferenceScale"/> to
    /// convert them into the units of the measured points.
    /// </remarks>
    [Combinator]
    [Description("Fits the rigid transform (Kabsch) mapping known reference points onto measured 3D points.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class KabschFit
    {
        double referenceScale = 1.0;
        int[] markerIds = new[] { 10, 11, 12, 13 };

        [FileNameFilter("JSON files (*.json)|*.json|All files (*.*)|*.*")]
        [Editor("Bonsai.Design.OpenFileNameEditor, Bonsai.Design", DesignTypes.UITypeEditor)]
        [Description("Optional calibration-sheet JSON (from generate_calibration_sheet.py) providing the reference marker centres. Overrides ReferencePoints when set.")]
        public string ReferenceFileName { get; set; }

        [Description("The marker ids to read from ReferenceFileName, in the same order as the measured points.")]
        public int[] MarkerIds
        {
            get { return markerIds; }
            set { markerIds = value; }
        }

        [Description("The reference points (e.g. marker centres in the arena frame), in the same order as the measured points. Used when ReferenceFileName is not set.")]
        public Vector3d[] ReferencePoints { get; set; }

        [Description("Scale applied to the reference points to convert them into the units of the measured points, e.g. 1 if both are in metres, or 100 if the reference is in metres and the detector MarkerSize was given in centimetres.")]
        public double ReferenceScale
        {
            get { return referenceScale; }
            set { referenceScale = value; }
        }

        public IObservable<RigidFit> Process(IObservable<Tuple<Vector3d, Vector3d, Vector3d>> source)
        {
            return Fit(source.Select(t => new[] { t.Item1, t.Item2, t.Item3 }));
        }

        public IObservable<RigidFit> Process(IObservable<Tuple<Vector3d, Vector3d, Vector3d, Vector3d>> source)
        {
            return Fit(source.Select(t => new[] { t.Item1, t.Item2, t.Item3, t.Item4 }));
        }

        public IObservable<RigidFit> Process(IObservable<Tuple<Vector3d, Vector3d, Vector3d, Vector3d, Vector3d>> source)
        {
            return Fit(source.Select(t => new[] { t.Item1, t.Item2, t.Item3, t.Item4, t.Item5 }));
        }

        public IObservable<RigidFit> Process(IObservable<Tuple<Vector3d, Vector3d, Vector3d, Vector3d, Vector3d, Vector3d>> source)
        {
            return Fit(source.Select(t => new[] { t.Item1, t.Item2, t.Item3, t.Item4, t.Item5, t.Item6 }));
        }

        public IObservable<RigidFit> Process(IObservable<Vector3d[]> source)
        {
            return Fit(source);
        }

        // Single-precision overloads, e.g. for points built with Bonsai.Shaders CreateVector3.
        public IObservable<RigidFit> Process(IObservable<Tuple<OpenTK.Vector3, OpenTK.Vector3, OpenTK.Vector3>> source)
        {
            return Fit(source.Select(t => new[] { D(t.Item1), D(t.Item2), D(t.Item3) }));
        }

        public IObservable<RigidFit> Process(IObservable<Tuple<OpenTK.Vector3, OpenTK.Vector3, OpenTK.Vector3, OpenTK.Vector3>> source)
        {
            return Fit(source.Select(t => new[] { D(t.Item1), D(t.Item2), D(t.Item3), D(t.Item4) }));
        }

        public IObservable<RigidFit> Process(IObservable<Tuple<OpenTK.Vector3, OpenTK.Vector3, OpenTK.Vector3, OpenTK.Vector3, OpenTK.Vector3>> source)
        {
            return Fit(source.Select(t => new[] { D(t.Item1), D(t.Item2), D(t.Item3), D(t.Item4), D(t.Item5) }));
        }

        public IObservable<RigidFit> Process(IObservable<Tuple<OpenTK.Vector3, OpenTK.Vector3, OpenTK.Vector3, OpenTK.Vector3, OpenTK.Vector3, OpenTK.Vector3>> source)
        {
            return Fit(source.Select(t => new[] { D(t.Item1), D(t.Item2), D(t.Item3), D(t.Item4), D(t.Item5), D(t.Item6) }));
        }

        public IObservable<RigidFit> Process(IObservable<OpenTK.Vector3[]> source)
        {
            return Fit(source.Select(points => points.Select(D).ToArray()));
        }

        static Vector3d D(OpenTK.Vector3 v)
        {
            return new Vector3d(v.X, v.Y, v.Z);
        }

        IObservable<RigidFit> Fit(IObservable<Vector3d[]> source)
        {
            return Observable.Defer(() =>
            {
                var reference = LoadReferencePoints();
                return source.Select(measured => Compute(reference, measured));
            });
        }

        Vector3d[] LoadReferencePoints()
        {
            Vector3d[] points;
            if (!string.IsNullOrEmpty(ReferenceFileName))
            {
                points = ReadCalibrationSheet(ReferenceFileName, MarkerIds);
            }
            else if (ReferencePoints != null && ReferencePoints.Length > 0)
            {
                points = ReferencePoints;
            }
            else
            {
                throw new InvalidOperationException("Either ReferenceFileName or ReferencePoints must be specified.");
            }

            var scale = ReferenceScale;
            return points.Select(p => new Vector3d(p.X * scale, p.Y * scale, p.Z * scale)).ToArray();
        }

        internal static Vector3d[] ReadCalibrationSheet(string fileName, int[] ids)
        {
            if (ids == null || ids.Length == 0)
            {
                throw new InvalidOperationException("MarkerIds must be specified when reading reference points from a file.");
            }

            var json = JObject.Parse(File.ReadAllText(fileName));
            var markers = json["markers"] as JArray;
            if (markers == null)
            {
                throw new InvalidOperationException(string.Format("'{0}' does not contain a 'markers' array.", fileName));
            }

            var centres = new Dictionary<int, Vector3d>();
            foreach (var marker in markers)
            {
                var c = (JArray)marker["center"];
                centres[(int)marker["id"]] = new Vector3d((double)c[0], (double)c[1], c.Count > 2 ? (double)c[2] : 0.0);
            }

            return ids.Select(id =>
            {
                Vector3d p;
                if (!centres.TryGetValue(id, out p))
                {
                    throw new InvalidOperationException(string.Format("Marker id {0} not found in '{1}'.", id, fileName));
                }
                return p;
            }).ToArray();
        }

        internal static RigidFit Compute(Vector3d[] reference, Vector3d[] measured)
        {
            if (measured == null || measured.Length != reference.Length)
            {
                throw new InvalidOperationException(string.Format(
                    "Expected {0} measured points to match the reference points but got {1}.",
                    reference.Length, measured == null ? 0 : measured.Length));
            }
            if (reference.Length < 3)
            {
                throw new InvalidOperationException("At least three point pairs are required.");
            }

            var n = reference.Length;
            var p = Matrix<double>.Build.Dense(3, n, (r, c) => Component(reference[c], r));
            var q = Matrix<double>.Build.Dense(3, n, (r, c) => Component(measured[c], r));
            var pMean = p.RowSums() / n;
            var qMean = q.RowSums() / n;
            var pc = p - Matrix<double>.Build.Dense(3, n, (r, c) => pMean[r]);
            var qc = q - Matrix<double>.Build.Dense(3, n, (r, c) => qMean[r]);

            // Cross-covariance and its SVD: H = U S V^T, R = V diag(1, 1, d) U^T.
            var h = pc * qc.Transpose();
            var svd = h.Svd(true);
            var u = svd.U;
            var v = svd.VT.Transpose();
            var s = svd.S;
            if (s[1] <= 1e-12 * Math.Max(s[0], 1e-300))
            {
                throw new InvalidOperationException("The reference or measured points are (nearly) collinear; the rotation is undetermined.");
            }

            var d = Math.Sign((v * u.Transpose()).Determinant());
            if (d == 0) d = 1;
            var correction = Matrix<double>.Build.DenseDiagonal(3, 3, 1.0);
            correction[2, 2] = d;
            var rotation = v * correction * u.Transpose();
            var translation = qMean - rotation * pMean;

            // Diagnostics.
            var fitted = rotation * p + Matrix<double>.Build.Dense(3, n, (r, c) => translation[r]);
            var residuals = Enumerable.Range(0, n).Select(c => (q.Column(c) - fitted.Column(c)).L2Norm()).ToArray();
            var referenceSpread = pc.Enumerate().Sum(x => x * x);
            var scaleRatio = referenceSpread > 0 ? (s[0] + s[1] + d * s[2]) / referenceSpread : double.NaN;

            var r2 = rotation.ToArray();
            var t = new Vector3d(translation[0], translation[1], translation[2]);
            var transform = new Matrix4(
                (float)r2[0, 0], (float)r2[1, 0], (float)r2[2, 0], 0f,
                (float)r2[0, 1], (float)r2[1, 1], (float)r2[2, 1], 0f,
                (float)r2[0, 2], (float)r2[1, 2], (float)r2[2, 2], 0f,
                (float)t.X, (float)t.Y, (float)t.Z, 1f);

            return new RigidFit
            {
                Rotation = r2,
                Translation = t,
                RotationVector = ToRotationVector(r2),
                Normal = new Vector3d(r2[0, 2], r2[1, 2], r2[2, 2]),
                Transform = transform,
                InverseTransform = Matrix4.Invert(transform),
                Residuals = residuals,
                RmsResidual = Math.Sqrt(residuals.Sum(x => x * x) / n),
                MaxResidual = residuals.Max(),
                ScaleRatio = scaleRatio
            };
        }

        static double Component(Vector3d point, int index)
        {
            return index == 0 ? point.X : index == 1 ? point.Y : point.Z;
        }

        // Rotation matrix -> Rodrigues vector via a quaternion (Shepperd's method), robust for all angles.
        static Vector3d ToRotationVector(double[,] r)
        {
            double w, x, y, z;
            var trace = r[0, 0] + r[1, 1] + r[2, 2];
            if (trace > 0)
            {
                var s = Math.Sqrt(trace + 1.0) * 2;
                w = 0.25 * s;
                x = (r[2, 1] - r[1, 2]) / s;
                y = (r[0, 2] - r[2, 0]) / s;
                z = (r[1, 0] - r[0, 1]) / s;
            }
            else if (r[0, 0] > r[1, 1] && r[0, 0] > r[2, 2])
            {
                var s = Math.Sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2;
                w = (r[2, 1] - r[1, 2]) / s;
                x = 0.25 * s;
                y = (r[0, 1] + r[1, 0]) / s;
                z = (r[0, 2] + r[2, 0]) / s;
            }
            else if (r[1, 1] > r[2, 2])
            {
                var s = Math.Sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2;
                w = (r[0, 2] - r[2, 0]) / s;
                x = (r[0, 1] + r[1, 0]) / s;
                y = 0.25 * s;
                z = (r[1, 2] + r[2, 1]) / s;
            }
            else
            {
                var s = Math.Sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2;
                w = (r[1, 0] - r[0, 1]) / s;
                x = (r[0, 2] + r[2, 0]) / s;
                y = (r[1, 2] + r[2, 1]) / s;
                z = 0.25 * s;
            }

            if (w < 0) { w = -w; x = -x; y = -y; z = -z; }
            var sinHalf = Math.Sqrt(x * x + y * y + z * z);
            if (sinHalf < 1e-12) return new Vector3d(0, 0, 0);
            var angle = 2 * Math.Atan2(sinHalf, w);
            return new Vector3d(x / sinHalf * angle, y / sinHalf * angle, z / sinHalf * angle);
        }
    }
}
