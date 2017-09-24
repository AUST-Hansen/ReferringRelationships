from keras import backend as K
from keras.applications.resnet50 import ResNet50
from keras.layers import Dense, Flatten, UpSampling2D, Reshape, Input, Activation
from keras.layers.core import Lambda, Dropout
from keras.layers.convolutional import Conv2DTranspose
from keras.layers.embeddings import Embedding
from keras.layers.merge import Dot, Concatenate, Multiply
from keras.models import Model


class ReferringRelationshipsModel():
    def __init__(self, model_params):
        self.input_dim = model_params["input_dim"]
        self.feat_map_dim = model_params["feat_map_dim"]
        self.hidden_dim = model_params["hidden_dim"]
        self.embedding_dim = model_params["embedding_dim"]
        self.num_subjects = model_params["num_subjects"]
        self.num_predicates = model_params["num_predicates"]
        self.num_objects = model_params["num_objects"]
        self.p_drop = model_params["p_drop"]
        self.upsampling_factor = self.input_dim / self.feat_map_dim

    def build_model(self):
        input_im = Input(shape=(self.input_dim, self.input_dim, 3))
        input_rel = Input(shape=(1,))
        input_obj = Input(shape=(1,))
        input_subj = Input(shape=(1,))
        images = self.build_image_model()(input_im)
        relationships = self.build_relationship_model(input_subj, input_rel, input_obj)
        relationships = Dropout(self.p_drop)(relationships)
        subjects_att = Dense(self.hidden_dim, activation='relu')(relationships)
        objects_att = Dense(self.hidden_dim, activation='relu')(relationships)
        subjects_att = Dropout(self.p_drop)(subjects_att)
        objects_att = Dropout(self.p_drop)(objects_att)
        subject_regions = self.build_attention_layer_2(images, subjects_att)
        object_regions = self.build_attention_layer_2(images, objects_att)
        model = Model(inputs=[input_im, input_subj, input_rel, input_obj], outputs=[subject_regions, object_regions])
        return model

    def build_image_model(self):
        base_model = ResNet50(weights='imagenet', include_top=False, input_shape=(self.input_dim, self.input_dim, 3))
        for layer in base_model.layers:
            layer.trainable = False
        output = base_model.get_layer('activation_40').output
        output = Dense(self.hidden_dim)(output)
        image_branch = Model(inputs=base_model.input, outputs=output)
        return image_branch

    def build_embedding_layer(self, input_vector, num_categories):
        embedding = Embedding(num_categories, self.embedding_dim, input_length=1)(input_vector)
        return embedding

    def build_relationship_model(self, input_subj, input_rel, input_obj):
        subj_embedding = self.build_embedding_layer(input_subj, self.num_subjects)
        predicate_embedding = self.build_embedding_layer(input_rel, self.num_predicates)
        obj_embedding = self.build_embedding_layer(input_obj, self.num_objects)
        concatenated_inputs = Concatenate(axis=2)([subj_embedding, predicate_embedding, obj_embedding])
        concatenated_inputs = Dropout(self.p_drop)(concatenated_inputs)
        concatenated_inputs = Dense(self.hidden_dim)(concatenated_inputs)
        return concatenated_inputs

    def build_attention_layer_1(self, images, relationships):
        images = Reshape(target_shape=(self.feat_map_dim * self.feat_map_dim, self.hidden_dim))(images)  # (196)x100
        merged = Dot(axes=(2, 2))([images, relationships])
        reshaped = Reshape(target_shape=(self.feat_map_dim, self.feat_map_dim, 1))(merged)
        upsampled = UpSampling2D(size=(self.upsampling_factor, self.upsampling_factor))(reshaped)
        flattened = Flatten()(upsampled)
        predictions = Activation('sigmoid')(flattened)
        return predictions

    def build_frac_strided_transposed_conv_layer(self, conv_layer):
        res = UpSampling2D(size=(2, 2))(conv_layer)
        res = Conv2DTranspose(1, 3, padding='same')(res)
        #res = BatchNormalization(momentum=0.9))(res)
        #res = Activation('relu')(res)
        return res

    def build_attention_layer_2(self, images, relationships):
        merged = Multiply()([images, relationships])
        merged = Lambda(lambda x: K.sum(x, axis=3))(merged)
        merged = Reshape(target_shape=(self.feat_map_dim, self.feat_map_dim, 1))(merged)
        upsampled = self.build_frac_strided_transposed_conv_layer(merged)
        upsampled = self.build_frac_strided_transposed_conv_layer(upsampled)
        upsampled = self.build_frac_strided_transposed_conv_layer(upsampled)
        upsampled = self.build_frac_strided_transposed_conv_layer(upsampled)
        flattened = Flatten()(upsampled)
        predictions = Activation('sigmoid')(flattened)
        return predictions


if __name__ == "__main__":
    from ReferringRelationships.config import params;
    rel = ReferringRelationshipsModel(params["model_params"])
    model = rel.build_model()
    model.summary()
