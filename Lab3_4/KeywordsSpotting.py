
import argparse
import numpy as np
import os
import tensorflow as tf
from tensorflow import keras

parser = argparse.ArgumentParser()
parser.add_argument('--model', type=str, required=False, default='MLP')
parser.add_argument('-mfcc', action='store_true')
parser.add_argument('-silence', action='store_true')
args = parser.parse_args()

#Set a seed to get repricable results
seed = 42
tf.random.set_seed(seed)
np.random.seed(seed)

class SignalGenerator:
	def __init__(self, labels, sampling_rate, frame_length, frame_step, num_mel_bins=None, lower_frequency=None, upper_frequency=None, num_coefficients=None, mfcc=False):
		self.labels=labels
		self.sampling_rate=sampling_rate
		self.frame_length=frame_length
		self.frame_step=frame_step
		self.num_mel_bins = num_mel_bins
		self.lower_frequency = lower_frequency
		self.upper_frequency = upper_frequency
		self.num_coefficients = num_coefficients
		self.mfccs=mfcc

		if(mfcc):
			num_spectrogram_bins = frame_length // 2 + 1
			self.linear_to_mel_weight_matrix = tf.signal.linear_to_mel_weight_matrix(
					self.num_mel_bins,
					num_spectrogram_bins,
					self.sampling_rate,
					self.lower_frequency,
					self.upper_frequency)
			self.preprocess = self.preprocess_with_mfcc
		else:
			self.preprocess = self.preprocess_with_stft


	def read(self, file_path):
		parts = tf.strings.split(file_path, os.path.sep)
		label = parts[-2]
		label_id = tf.argmax(label == self.labels)
		audio_bynary = tf.io.read_file(file_path)
		audio, _ = tf.audio.decode_wav(audio_bynary)
		#print('Sampling: ', np.array(r))
		audio = tf.squeeze(audio, axis=1)
		return audio, label_id

	def pad(self, audio):
		zero_padding = tf.zeros(self.sampling_rate - tf.shape(audio), dtype=tf.float32)
		audio = tf.concat([audio,zero_padding],0)
		audio.set_shape([self.sampling_rate])
		return audio

	def get_spectrogram(self, audio):
		#Calculate the STFT of the signal given frame_length and frame_step
		stft = tf.signal.stft(audio,
						frame_length=self.frame_length,
						frame_step=self.frame_step,
						fft_length=self.frame_length)
		#Transform the complex number in real number
		spectrogram = tf.abs(stft)
		return spectrogram

	def get_mfccs(self, spectrogram):
		mel_spectrogram = tf.tensordot(spectrogram,
						self.linear_to_mel_weight_matrix, 1)
		log_mel_spectrogram = tf.math.log(mel_spectrogram + 1.e-6)
		mfccs = tf.signal.mfccs_from_log_mel_spectrograms(log_mel_spectrogram)
		mfccs = mfccs[:, :self.num_coefficients]
		return mfccs

	def preprocess_with_stft(self, file_path):
		audio, label = self.read(file_path)
		audio = self.pad(audio)
		spectrogram = self.get_spectrogram(audio)
		spectrogram = tf.expand_dims(spectrogram, -1)
		spectrogram  = tf.image.resize(spectrogram, [32,32])
		return spectrogram, label

	def preprocess_with_mfcc(self, file_path):
		audio, label = self.read(file_path)
		audio = self.pad(audio)
		spectrogram = self.get_spectrogram(audio)
		mfccs = self.get_mfccs(spectrogram)
		mfccs = tf.expand_dims(mfccs, -1)
		return mfccs, label

	def make_dataset(self, files, train=False):
		#This method creates a dataset from a numpy array (our listfile path)
		ds = tf.data.Dataset.from_tensor_slices(files)
		#Different preprocess step depending on the input parameter
		ds = ds.map(self.preprocess, num_parallel_calls=4)
		ds = ds.batch(32)
		ds = ds.cache()

		if(train is True):
			ds = ds.shuffle(100, reshuffle_each_iteration=True)
		return ds

class Model:
	def __init__(self,model_type,mfcc,silence):
		if(silence):
			self.n_output = 9
		else:
			self.n_output = 8
		if(mfcc):
			self.strides = [2,1]
		else:
			self.strides = [2,2]
		if(model_type=='MLP'):
			self.model = self.MLPmodel()
		elif(model_type=='CNN'):
			self.model = self.CNNmodel()
		elif(model_type=='DSCNN'):
			self.model = self.DSCNNmodel()
		self.model.compile(optimizer='adam', loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True), metrics=[tf.metrics.SparseCategoricalAccuracy()])
		self.checkpoint_path = 'KSckp/'
		self.model_checkpoint_callback = tf.keras.callbacks.ModelCheckpoint(
									filepath=self.checkpoint_path,
									save_weights_only=True,
									monitor='sparse_categorical_accuracy',
									mode='max',
									save_best_only=True)

	def MLPmodel(self):
		model = keras.Sequential([
					keras.layers.Flatten(),
					keras.layers.Dense(256, activation='relu'),
					keras.layers.Dense(256, activation='relu'),
					keras.layers.Dense(256, activation='relu'),
					keras.layers.Dense(self.n_output)
				])
		return model
	#Strides = [2,2] if STFT, [2,1] if MFCC
	def CNNmodel(self):
		model = keras.Sequential([
					keras.layers.Conv2D(filters=128,kernel_size=[3,3],strides=self.strides,use_bias=False),
					keras.layers.BatchNormalization(momentum=0.1),
					keras.layers.Activation('relu'),
					keras.layers.Conv2D(filters=128,kernel_size=[3,3],strides=[1,1],use_bias=False),
					keras.layers.BatchNormalization(momentum=0.1),
					keras.layers.Activation('relu'),
					keras.layers.Conv2D(filters=128,kernel_size=[3,3],strides=[1,1],use_bias=False),
					keras.layers.BatchNormalization(momentum=0.1),
					keras.layers.Activation('relu'),
					keras.layers.GlobalAveragePooling2D(),
					keras.layers.Dense(self.n_output)
				])
		return model
	def DSCNNmodel(self):
		model = keras.Sequential([
					keras.layers.Conv2D(filters=256,kernel_size=[3,3],strides=self.strides,use_bias=False), #input_shape=(32,32,1)
					keras.layers.BatchNormalization(momentum=0.1),
					keras.layers.Activation('relu'),
					keras.layers.DepthwiseConv2D(kernel_size=[3, 3], strides=[1, 1], use_bias=False),
					keras.layers.Conv2D(filters=256,kernel_size=[1,1],strides=[1,1],use_bias=False),
					keras.layers.BatchNormalization(momentum=0.1),
					keras.layers.Activation('relu'),
					keras.layers.DepthwiseConv2D(kernel_size=[3, 3], strides=[1, 1], use_bias=False),
					keras.layers.Conv2D(filters=256,kernel_size=[1,1],strides=[1, 1],use_bias=False),
					keras.layers.BatchNormalization(momentum=0.1),
					keras.layers.Activation('relu'),
					keras.layers.GlobalAveragePooling2D(),
					keras.layers.Dense(self.n_output)
				])
		return model

	def Train(self,train,validation,epoch):
		print('Training')
		history = self.model.fit(train, batch_size=32, epochs=epoch, verbose=1, validation_data=validation, validation_freq=2, callbacks=self.model_checkpoint_callback)
		return history

	def Test(self, test):
		print('Evaluation')
		self.model.load_weights(self.checkpoint_path)
		loss, error = self.model.evaluate(test, verbose=1)
		return (loss, error)

	def SaveModel(self,output):
		#run_model = tf.function(lambda x: self.model(x))
		#concrete_func = run_model.get_concrete_function(tf.TensorSpec([1,6,2], tf.float32))
		self.model.save(output) #, signatures=concrete_func)

model = args.model
mfcc = args.mfcc
silence = args.silence

#Download and extract the .csv file. The result is cached to avoid to download everytime
zip_path = tf.keras.utils.get_file(
	origin='http://storage.googleapis.com/download.tensorflow.org/data/mini_speech_commands.zip',
	fname='mini_speech_commands.zip',
	extract=True,
	cache_dir='.', cache_subdir='data')

data_dir = os.path.join('.', 'data', 'mini_speech_commands')
#Store in a list all files as a string inside a given path
filenames = tf.io.gfile.glob(str(data_dir) + '/*/*')
#Shuffle to have a uniform distribution of the samples
if(silence is False):
	filenames = [x for x in filenames if x.find('silence')<0]
filenames = tf.random.shuffle(filenames)
num_samples = len(filenames)

train_files = filenames[:int(num_samples*0.8)]
validation_files = filenames[int(num_samples*0.8):int(num_samples*0.9)]
test_files = filenames[int(num_samples*0.9):]


#Extract the labes: folders inside the data folder
LABELS = np.array(tf.io.gfile.listdir(str(data_dir)))
#Remove the 'README.md' file, since not useful
LABELS = LABELS[LABELS != 'README.md']

if(silence is False):
	LABELS = LABELS[LABELS != 'silence']

if(mfcc):
	sg = SignalGenerator(labels=LABELS, sampling_rate=16000, frame_length=640, frame_step=320,
				num_mel_bins=40, lower_frequency=20, upper_frequency=4000, num_coefficients=10, mfcc=mfcc)
else:
	sg = SignalGenerator(labels=LABELS, sampling_rate=16000, frame_length=256, frame_step=128)

train_ds = sg.make_dataset(train_files,True)
val_ds = sg.make_dataset(validation_files)
test_ds = sg.make_dataset(test_files)
print(f'Train: {len(train_ds)}, Val: {len(val_ds)}, Test: {len(test_ds)}')

#for x,y in train_ds.take(1):
#	print(x.shape,y.shape)

for m in ['MLP', 'CNN', 'DSCNN']:
	for f in [False, True]:
		print(f'\n\nModel: {m}, mfcc: {f}')
		model = m
		mfcc = f

		model = Model(model,mfcc,silence)
		hist = model.Train(train_ds,val_ds,20)
		loss, error = model.Test(test_ds)
		print('Evaluation Error: ',error)
		model.model.summary()
model.SaveModel('model/')
